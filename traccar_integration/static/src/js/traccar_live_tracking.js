/** @odoo-module **/

(function() {
    'use strict';

    // Global variables
    let map = null;
    let deviceMarkers = {};
    let allDevices = [];
    let leafletLoaded = false;
    let isInitialized = false;
    let pollingInterval = null;
    let lastPositionCheck = new Date();
    let browserSyncInterval = 30;
    let hasInitialCentered = false;
    let syncInFlight = false;
    let checkInFlight = false;
    let positionsInFlight = false;
    let syncCooldownUntil = null;

    let replayPolyline = null; // This will now be an array or FeatureGroup
    let replayMarkers = [];
    let isReplayMode = false;
    let selectedDeviceId = null;

    // Playback state
    let playbackPositions = [];
    let playbackIndex = 0;
    let playbackTimer = null;
    let playbackMarker = null;
    let isPlaying = false;

    // Configuration
    const INITIAL_LOAD_DELAY = 800;
    const POLLING_INTERVAL = 1000;
    const REQUEST_TIMEOUT = 15000;
    const SYNC_FAILURE_COOLDOWN = 60000;

    function updateStatus(message, type) {
        try {
            const statusElement = document.getElementById('header_status_text');
            const spinner = document.getElementById('header_status_spinner');
            const badge = document.getElementById('header_status_badge');
            if (!statusElement) return;
            
            statusElement.textContent = message;
            
            if (spinner) {
                if (message === "Syncing...") {
                    spinner.classList.remove('d-none');
                } else {
                    spinner.classList.add('d-none');
                }
            }

            if (badge) {
                // Reset classes
                badge.classList.remove('bg-info-light', 'bg-danger-light', 'bg-success-light', 'text-info', 'text-danger', 'text-success', 'border-info', 'border-danger', 'border-success');
                
                if (type === 'danger' || message.includes('Error')) {
                    badge.classList.add('bg-danger-light', 'text-danger', 'border-danger');
                } else if (type === 'success' || message === 'Online') {
                    badge.classList.add('bg-success-light', 'text-success', 'border-success');
                } else {
                    badge.classList.add('bg-info-light', 'text-info', 'border-info');
                }
            }
        } catch (error) {
            console.error('Status error:', error);
        }
    }

    function initializeWhenReady() {
        const mapElement = document.getElementById('traccar_live_map');
        if (mapElement && !isInitialized && !window._traccar_initializing) {
            window._traccar_initializing = true;
            console.info('Initializing Premium Dashboard...');
            
            fetchSyncConfiguration().then(() => {
                setTimeout(() => {
                    loadLeafletAndInit();
                    setupEventListeners();
                    triggerBrowserSync();
                    window._traccar_initializing = false;
                }, INITIAL_LOAD_DELAY);
            }).catch(() => {
                window._traccar_initializing = false;
            });
        } 
        setTimeout(initializeWhenReady, 1500);
    }

    function fetchSyncConfiguration() {
        return new Promise((resolve) => {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/web/dataset/call_kw', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.timeout = REQUEST_TIMEOUT;

            const data = {
                jsonrpc: "2.0",
                method: "call",
                params: {
                    model: "traccar.config",
                    method: "get_browser_sync_interval",
                    args: [],
                    kwargs: {}
                },
                id: Math.floor(Math.random() * 1000000)
            };

            xhr.onreadystatechange = function() {
                if (xhr.readyState === 4) {
                    if (xhr.status === 200) {
                        try {
                            const response = JSON.parse(xhr.responseText);
                            if (response.result) {
                                browserSyncInterval = parseInt(response.result) || 30;
                            }
                        } catch (e) {}
                    }
                    resolve();
                }
            };
            xhr.send(JSON.stringify(data));
        });
    }

    function setupEventListeners() {
        // Search Functionality
        const searchInput = document.getElementById('device_search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                const term = e.target.value.toLowerCase();
                filterDevices(term);
            });
        }

        // Fullscreen Toggle
        const toggleBtn = document.getElementById('btn_toggle_fullscreen');
        if (toggleBtn) {
            if (window.L) {
                L.DomEvent.disableClickPropagation(toggleBtn);
                L.DomEvent.disableScrollPropagation(toggleBtn);
            }
            toggleBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                toggleMapExpansion();
            };
        }

        // Fit Bounds Button
        const fitBtn = document.getElementById('btn_fit_bounds');
        if (fitBtn) {
            if (window.L) {
                L.DomEvent.disableClickPropagation(fitBtn);
                L.DomEvent.disableScrollPropagation(fitBtn);
            }
            fitBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                autoCenterMap();
            }
        }

        // Manual Refresh
        const refreshBtn = document.querySelector('button[name="sync_all_data"]');
        if (refreshBtn) {
            refreshBtn.onclick = (e) => {
                e.preventDefault();
                loadDevicePositions();
            };
        }
        startPositionPolling();
        setupReplayListeners();
    }

    function setupReplayListeners() {
        const confirmBtn = document.getElementById('btn_confirm_replay');
        const closeBtn = document.querySelector('.btn-close-replay');
        
        if (confirmBtn) confirmBtn.onclick = confirmReplay;
        if (closeBtn) closeBtn.onclick = () => toggleReplayDialog(false);

        // Playback listeners
        const playPauseBtn = document.getElementById('btn_play_pause');
        const replaySlider = document.getElementById('replay_slider');
        const speedSelect = document.getElementById('playback_speed_mult');

        if (playPauseBtn) playPauseBtn.onclick = togglePlayback;
        if (replaySlider) {
            replaySlider.oninput = (e) => seekTo(parseInt(e.target.value));
        }
        if (speedSelect) {
            speedSelect.onchange = () => {
                if (isPlaying) {
                    pausePlayback();
                    startPlayback();
                }
            };
        }

        // Global hook for the sidebar button
        window._traccar_toggle_replay = (id) => {
            toggleReplayDialog(true);
            // Default From to 24h ago, To to Now
            const now = new Date();
            const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            
            // Format for datetime-local (yyyy-MM-ddThh:mm)
            const fmt = (d) => d.toISOString().slice(0, 16);
            document.getElementById('replay_from').value = fmt(yesterday);
            document.getElementById('replay_to').value = fmt(now);
        };
    }

    function filterDevices(term) {
        const filtered = allDevices.filter(d => 
            (d.name && d.name.toLowerCase().includes(term)) || 
            (d.unique_id && d.unique_id.toString().includes(term))
        );
        renderDeviceList(filtered);
        
        // Show/Hide markers based on search
        for (const id in deviceMarkers) {
            const marker = deviceMarkers[id];
            const isVisible = filtered.some(d => d.id == id);
            if (isVisible) marker.addTo(map);
            else map.removeLayer(marker);
        }
    }

    function startPositionPolling() {
        if (pollingInterval) clearInterval(pollingInterval);
        let syncCounter = 0;
        pollingInterval = setInterval(() => {
            if (!document.getElementById('traccar_live_map')) {
                clearInterval(pollingInterval);
                pollingInterval = null;
                isInitialized = false;
                return;
            }
            checkForNewPositions();
            syncCounter++;
            if (syncCounter >= browserSyncInterval) {
                triggerBrowserSync();
                syncCounter = 0;
            }
        }, POLLING_INTERVAL);
    }

    function triggerBrowserSync() {
        if (syncInFlight) return;
        const now = Date.now();
        if (syncCooldownUntil && now < syncCooldownUntil) return;

        syncInFlight = true;
        updateStatus("Syncing...", "info");

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/web/dataset/call_kw', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.timeout = REQUEST_TIMEOUT;

        const data = {
            jsonrpc: "2.0",
            method: "call",
            params: {
                model: "traccar.config",
                method: "action_browser_sync",
                args: [],
                kwargs: {}
            },
            id: Math.floor(Math.random() * 1000000)
        };

        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                syncInFlight = false;
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.result) {
                            setTimeout(() => {
                                checkForNewPositions();
                            }, 1000);
                            updateStatus("Online", "success");
                            syncCooldownUntil = null;
                        } else {
                            updateStatus("Up to date", "success");
                        }
                    } catch (e) {
                        updateStatus("Error", "danger");
                    }
                } else {
                    syncCooldownUntil = Date.now() + SYNC_FAILURE_COOLDOWN;
                    updateStatus("Retry soon", "warning");
                }
            }
        };
        xhr.send(JSON.stringify(data));
    }

    function checkForNewPositions() {
        if (checkInFlight || positionsInFlight) return;
        checkInFlight = true;

        // Use a 5-minute safety overlap to account for clock skew between browser and server
        const safetyMargin = 5 * 60 * 1000;
        const checkTime = new Date(lastPositionCheck.getTime() - safetyMargin);
        
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/web/dataset/call_kw', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.timeout = 5000;

        const data = {
            jsonrpc: "2.0",
            method: "call",
            params: {
                model: "traccar.position",
                method: "search_count",
                args: [],
                kwargs: {
                    domain: [["create_date", ">", checkTime.toISOString()], ["device_id", "!=", false]]
                }
            },
            id: Math.floor(Math.random() * 1000000)
        };

        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                checkInFlight = false;
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.result && response.result > 0) {
                            lastPositionCheck = new Date();
                            loadDevicePositions();
                        }
                    } catch (e) {}
                }
            }
        };
        xhr.send(JSON.stringify(data));
    }

    function loadLeafletAndInit() {
        if (window.L) {
            leafletLoaded = true;
            initializeLiveTracking();
            return;
        }
        const cssLink = document.createElement('link');
        cssLink.rel = 'stylesheet';
        cssLink.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
        document.head.appendChild(cssLink);

        const script = document.createElement('script');
        script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
        script.onload = () => {
            leafletLoaded = true;
            initializeLiveTracking();
        };
        document.head.appendChild(script);
    }

    function initializeLiveTracking() {
        if (isInitialized) return;
        const mapElement = document.getElementById('traccar_live_map');
        if (!mapElement) return;

        // Reset state variables to ensure fresh markers on the new map instance
        deviceMarkers = {};
        allDevices = [];
        hasInitialCentered = false;

        // Initialize Map
        map = L.map('traccar_live_map', { zoomControl: false }).setView([30.0444, 31.2357], 10);
        L.control.zoom({ position: 'bottomright' }).addTo(map);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap',
            maxZoom: 19
        }).addTo(map);

        loadDevicePositions();
        isInitialized = true;
    }

    function loadDevicePositions() {
        if (positionsInFlight) return;
        positionsInFlight = true;

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/web/dataset/call_kw', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.timeout = REQUEST_TIMEOUT;

        const data = {
            jsonrpc: "2.0",
            method: "call",
            params: {
                model: "traccar.device",
                method: "search_read",
                args: [],
                kwargs: {
                    fields: ["name", "unique_id", "status", "last_update", "latitude", "longitude", "battery"],
                    domain: [
                        ["unique_id", "!=", "DASHBOARD_ONLY"]
                    ],
                    limit: 100,
                    order: "write_date desc"
                }
            },
            id: Math.floor(Math.random() * 1000000)
        };

        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                positionsInFlight = false;
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.result) {
                            allDevices = response.result;
                            processDevicesData(allDevices);
                        }
                    } catch (e) {}
                }
            }
        };
        xhr.send(JSON.stringify(data));
    }

    function processDevicesData(devices) {
        if (!devices || !map) return;
        devices.forEach(device => addDeviceMarker(device));
        renderDeviceList(devices);
        updateStatistics(devices);
        if (!hasInitialCentered && devices.length > 0) {
            autoCenterMap();
            hasInitialCentered = true;
        }
    }

    function renderDeviceList(devices) {
        const container = document.getElementById('device_list_container');
        if (!container) return;
        
        if (devices.length === 0) {
            container.innerHTML = '<div class="p-4 text-center text-muted">No devices found</div>';
            return;
        }

        container.innerHTML = devices.map(device => `
            <div class="device-item ${selectedDeviceId === device.id ? 'active' : ''}" data-id="${device.id}">
                <div class="device-item-header">
                    <div class="device-item-info">
                        <div class="device-item-name">${device.name}</div>
                        <div class="device-item-sub">
                            <i class="fa fa-microchip"></i> ${device.unique_id}
                            ${device.battery > 0 ? ` · <span class="battery-badge ${device.battery < 20 ? 'battery-low' : ''}">${device.battery}%</span>` : ''}
                        </div>
                        ${selectedDeviceId === device.id ? `
                            <button class="btn-replay-sidebar">
                                <i class="fa fa-history"></i> Replay Route
                            </button>
                        ` : ''}
                    </div>
                    <span class="device-status-dot status-${device.status || 'unknown'}"></span>
                </div>
            </div>
        `).join('');

        // Add Click Events
        container.querySelectorAll('.device-item').forEach(item => {
            item.onclick = function(e) {
                // If clicked replay button specifically, toggle dialog
                if (e.target.closest('.btn-replay-sidebar')) {
                    const id = this.getAttribute('data-id');
                    window._traccar_toggle_replay(id);
                    return;
                }
                const id = this.getAttribute('data-id');
                selectDevice(id);
            };
        });
    }

    function selectDevice(id) {
        selectedDeviceId = parseInt(id);
        const device = allDevices.find(d => d.id === selectedDeviceId);
        if (device && device.latitude && device.longitude) {
            // center map on device
            if (map) map.flyTo([device.latitude, device.longitude], 15);
            
            // open popup
            if (deviceMarkers[selectedDeviceId]) {
                deviceMarkers[selectedDeviceId].openPopup();
            }

            // Update UI list to show active state and button
            renderDeviceList(allDevices);
        }
    }

    function addDeviceMarker(device) {
        if (isReplayMode) return; 

        const lat = parseFloat(device.latitude);
        const lng = parseFloat(device.longitude);
        if (isNaN(lat) || isNaN(lng)) return;
        if (lat === 0 && lng === 0) return; // Safety check: ignore 0,0 positions

        const iconColor = device.status === 'online' ? '#10b981' : (device.status === 'offline' ? '#ef4444' : '#f59e0b');
        const customIcon = L.divIcon({
            className: 'custom-device-marker',
            html: `<div class="marker-inner" style="background: ${iconColor};"></div>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        });

        if (deviceMarkers[device.id]) {
            deviceMarkers[device.id].setLatLng([lat, lng]);
            deviceMarkers[device.id].setPopupContent(createPopupContent(device));
        } else {
            deviceMarkers[device.id] = L.marker([lat, lng], { icon: customIcon })
                .addTo(map)
                .bindPopup(createPopupContent(device));
        }
    }

    function createPopupContent(device) {
        return `
            <div class="traccar-popup">
                <div class="popup-header">
                    <strong>${device.name || 'Device'}</strong>
                </div>
                <div class="popup-body">
                    <div class="popup-info-row">
                        <i class="fa fa-map-marker text-primary"></i>
                        <span>${device.latitude.toFixed(6)}, ${device.longitude.toFixed(6)}</span>
                    </div>
                    <div class="popup-info-row">
                        <i class="fa fa-clock-o"></i>
                        <span>${new Date(device.last_update).toLocaleString()}</span>
                    </div>
                    ${device.battery > 0 ? `
                    <div class="popup-info-row">
                        <i class="fa fa-battery-half"></i>
                        <span>Battery: ${device.battery}%</span>
                    </div>` : ''}
                    <div class="popup-badge status-${device.status || 'unknown'}">${(device.status || 'unknown').toUpperCase()}</div>
                </div>
            </div>
        `;
    }

    function autoCenterMap() {
        if (!map || Object.keys(deviceMarkers).length === 0) return;
        const group = new L.featureGroup(Object.values(deviceMarkers));
        map.fitBounds(group.getBounds(), { padding: [50, 50] });
    }

    function updateStatistics(devices) {
        const totalEl = document.getElementById('total_devices');
        const onlineEl = document.getElementById('online_devices');
        const offlineEl = document.getElementById('offline_devices');
        const unknownEl = document.getElementById('unknown_devices');
        if (totalEl) totalEl.textContent = devices.length;
        if (onlineEl) onlineEl.textContent = devices.filter(d => d.status === 'online').length;
        if (offlineEl) offlineEl.textContent = devices.filter(d => d.status === 'offline').length;
        if (unknownEl) unknownEl.textContent = devices.filter(d => d.status === 'unknown').length;
    }

    function toggleMapExpansion() {
        console.log('Toggle Map Expansion triggered');
        const btn = document.getElementById('btn_toggle_fullscreen');
        let wrapper = document.querySelector('.traccar-dashboard-wrapper');
        
        // Fallback: search up from the button if selector fails
        if (!wrapper && btn) {
            wrapper = btn.closest('.traccar-dashboard-wrapper');
        }

        if (!wrapper) {
            console.error('Traccar Dashboard Wrapper not found!');
            return;
        }

        const isExpanded = wrapper.classList.toggle('map-expanded');
        console.log('Map Expanded state:', isExpanded);
        
        // Update Icon
        if (btn) {
            const icon = btn.querySelector('i');
            if (icon) {
                icon.className = isExpanded ? 'fa fa-compress' : 'fa fa-arrows-alt';
            }
            btn.title = isExpanded ? 'Collapse Map' : 'Expand Map';
        }

        // Critical: Update Leaflet size after transition
        setTimeout(() => {
            if (map) {
                console.log('Invalidating map size...');
                map.invalidateSize({ animate: true });
                if (isExpanded) {
                    autoCenterMap();
                }
            }
        }, 400); // Slightly longer timeout to ensure transition finished
    }

    // -------------------------------
    // Replay Logic
    // -------------------------------
    function toggleReplayDialog(show) {
        const overlay = document.getElementById('traccar_replay_overlay');
        if (overlay) overlay.classList.toggle('d-none', !show);
        if (!show) clearReplay();
    }

    function confirmReplay() {
        const from = document.getElementById('replay_from').value;
        const to = document.getElementById('replay_to').value;
        const status = document.getElementById('replay_status');

        if (!from || !to || !selectedDeviceId) return;

        status.classList.remove('d-none');
        isReplayMode = true;

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/web/dataset/call_kw', true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.timeout = 30000;

        const data = {
            jsonrpc: "2.0",
            method: "call",
            params: {
                model: "traccar.position",
                method: "search_read",
                args: [],
                kwargs: {
                    domain: [
                        ['device_id', '=', selectedDeviceId],
                        ['device_time', '>=', from],
                        ['device_time', '<=', to]
                    ],
                    fields: ['latitude', 'longitude', 'device_time', 'speed_kmh', 'course'],
                    order: 'device_time asc',
                    limit: 1000
                }
            },
            id: Math.floor(Math.random() * 1000000)
        };

        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                status.classList.add('d-none');
                if (xhr.status === 200) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.result && response.result.length > 0) {
                            drawRoute(response.result);
                        } else {
                            alert("No route data found for this period.");
                        }
                    } catch (e) {
                        console.error('Replay parse error:', e);
                    }
                } else {
                    alert("Failed to fetch route history from server.");
                }
            }
        };
        xhr.send(JSON.stringify(data));
    }

    function getSpeedColor(speed) {
        if (speed < 10) return '#ef4444'; // Red
        if (speed < 40) return '#f97316'; // Orange
        if (speed < 80) return '#0ea5e9'; // Blue (Moved away from Yellow for contrast)
        return '#10b981'; // Green
    }

    function calculateDistance(lat1, lon1, lat2, lon2) {
        const R = 6371; // km
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                  Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                  Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    function drawRoute(positions) {
        clearReplay();
        playbackPositions = positions;
        
        // Show playback UI
        document.getElementById('playback_container').classList.remove('d-none');
        
        const slider = document.getElementById('replay_slider');
        const distanceEl = document.getElementById('replay_total_distance');
        
        if (slider) {
            slider.max = positions.length - 1;
            slider.value = 0;
        }

        // Calculate total distance
        let totalDistance = 0;
        for (let i = 0; i < positions.length - 1; i++) {
            totalDistance += calculateDistance(
                positions[i].latitude, positions[i].longitude,
                positions[i+1].latitude, positions[i+1].longitude
            );
        }
        if (distanceEl) {
            distanceEl.textContent = totalDistance.toFixed(2) + ' km';
        }

        // FeatureGroup to hold all arrows
        replayPolyline = L.featureGroup().addTo(map);
        
        // Add Direction Arrows at EVERY point for maximum visibility
        positions.forEach((p, index) => {
            if (index > 0 && index < positions.length - 1) {
                const rotation = p.course || 0;
                const speed = p.speed_kmh || 0;
                const speedColor = getSpeedColor(speed);
                
                const arrowIcon = L.divIcon({
                    className: 'replay-arrow',
                    html: `<div style="transform: rotate(${rotation}deg); color: ${speedColor};">
                             <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                               <path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>
                             </svg>
                           </div>`,
                    iconSize: [20, 20],
                    iconAnchor: [10, 10]
                });
                L.marker([p.latitude, p.longitude], { 
                    icon: arrowIcon,
                    interactive: false 
                }).addTo(replayPolyline);
            }
        });

        // Zoom to route
        map.fitBounds(replayPolyline.getBounds(), { padding: [60, 60] });

        // Markers for Start and Finish
        const start = positions[0];
        const end = positions[positions.length - 1];

        const startMarker = L.circleMarker([start.latitude, start.longitude], {
            radius: 10, color: 'white', fillColor: '#10b981', fillOpacity: 1, weight: 3
        }).addTo(map);
        
        const startLabel = L.marker([start.latitude, start.longitude], {
            icon: L.divIcon({
                className: 'point-label start',
                html: 'START',
                iconSize: [50, 20],
                iconAnchor: [25, 35]
            })
        }).addTo(map);

        // Finish Point
        const finishMarker = L.circleMarker([end.latitude, end.longitude], {
            radius: 10, color: 'white', fillColor: '#ef4444', fillOpacity: 1, weight: 3
        }).addTo(map);

        const finishLabel = L.marker([end.latitude, end.longitude], {
            icon: L.divIcon({
                className: 'point-label finish',
                html: 'FINISH',
                iconSize: [50, 20],
                iconAnchor: [25, 35]
            })
        }).addTo(map);

        // Add playback marker (the "car")
        const carIcon = L.divIcon({
            className: 'playback-marker',
            html: '<div class="playback-marker-inner"><i class="fa fa-car"></i></div>',
            iconSize: [32, 32],
            iconAnchor: [16, 16]
        });
        playbackMarker = L.marker([start.latitude, start.longitude], { icon: carIcon, zIndexOffset: 1000 }).addTo(map);

        replayMarkers.push(startMarker, startLabel, finishMarker, finishLabel, playbackMarker);
        
        // Add Speed Legend if not already there
        if (!document.querySelector('.speed-legend')) {
            const legend = document.createElement('div');
            legend.className = 'speed-legend';
            legend.innerHTML = `
                <div class="legend-item"><div class="legend-color" style="background:#ef4444"></div><span>&lt; 10 km/h</span></div>
                <div class="legend-item"><div class="legend-color" style="background:#f97316"></div><span>10-40 km/h</span></div>
                <div class="legend-item"><div class="legend-color" style="background:#0ea5e9"></div><span>40-80 km/h</span></div>
                <div class="legend-item"><div class="legend-color" style="background:#10b981"></div><span>&gt; 80 km/h</span></div>
            `;
            document.querySelector('.traccar-map-section').appendChild(legend);
        }

        seekTo(0);
    }

    // -------------------------------
    // Playback Engine
    // -------------------------------
    function togglePlayback() {
        if (isPlaying) pausePlayback();
        else startPlayback();
    }

    function startPlayback() {
        if (isPlaying || playbackPositions.length === 0) return;
        isPlaying = true;
        document.getElementById('btn_play_pause').innerHTML = '<i class="fa fa-pause"></i>';
        
        const multiplier = parseInt(document.getElementById('playback_speed_mult').value) || 1;
        const interval = 1000 / (multiplier * 2); // 2 steps per second base
        
        playbackTimer = setInterval(() => {
            if (playbackIndex < playbackPositions.length - 1) {
                playbackIndex++;
                updatePlaybackUI();
            } else {
                pausePlayback();
            }
        }, interval);
    }

    function pausePlayback() {
        isPlaying = false;
        if (playbackTimer) clearInterval(playbackTimer);
        document.getElementById('btn_play_pause').innerHTML = '<i class="fa fa-play"></i>';
    }

    function seekTo(index) {
        playbackIndex = index;
        updatePlaybackUI();
    }

    function updatePlaybackUI() {
        const p = playbackPositions[playbackIndex];
        if (!p || !playbackMarker) return;

        playbackMarker.setLatLng([p.latitude, p.longitude]);
        
        // Update slider
        const slider = document.getElementById('replay_slider');
        if (slider) slider.value = playbackIndex;

        // Update time and speed text
        const timeEl = document.getElementById('replay_current_time');
        const speedEl = document.getElementById('replay_current_speed');
        
        if (timeEl) {
            const date = new Date(p.device_time);
            timeEl.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        }
        if (speedEl) {
            speedEl.textContent = Math.round(p.speed_kmh || 0) + ' km/h';
        }

        // Optional: Map follows car
        // map.panTo([p.latitude, p.longitude]);
    }

    function clearReplay() {
        pausePlayback();
        playbackPositions = [];
        playbackIndex = 0;
        
        const pbContainer = document.getElementById('playback_container');
        if (pbContainer) pbContainer.classList.add('d-none');

        const legend = document.querySelector('.speed-legend');
        if (legend) legend.remove();

        if (replayPolyline) {
            map.removeLayer(replayPolyline);
            replayPolyline = null;
        }
        replayMarkers.forEach(m => map.removeLayer(m));
        replayMarkers = [];
        isReplayMode = false;
        
        // Return to live view by showing all markers again
        loadDevicePositions();
    }

    initializeWhenReady();

})();