/** @odoo-module **/

import { Component, onWillStart, onMounted, onWillUnmount, useState, useRef, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

class SalesRepDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        // Refs for charts
        this.routeChartRef = useRef("routeChart");
        this.visitChartRef = useRef("visitChart");
        this.efficiencyGaugeRef = useRef("efficiencyGauge");

        // UI State
        this.state = useState({
            date_from: new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0],
            date_to: new Date().toISOString().split('T')[0],
            sales_rep_id: "",
            reps: [],
            data: {
                kpis: {
                    total_routes: 0,
                    completed_routes: 0,
                    total_visits: 0,
                    completed_visits: 0,
                    total_sales: 0,
                    total_payments: 0,
                    route_completion: 0,
                    visit_completion: 0,
                    efficiency: 0,
                },
                route_status_data: [],
                daily_visit_data: [],
            },
        });

        // Lifecycle
        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadInitialData();
            await this.refreshData();
        });

        onMounted(() => {
            this.renderCharts();
        });

        onWillUnmount(() => {
            this.destroyCharts();
        });

        // Reactivity for charts
        useEffect(() => {
            this.renderCharts();
        }, () => [this.state.data]);
    }

    async loadInitialData() {
        // Fetch sales representatives for the filter dropdown
        const reps = await this.orm.searchRead(
            "sales.representative",
            [],
            ["id", "name"]
        );
        this.state.reps = reps;
    }

    async refreshData() {
        const result = await this.orm.call(
            "sales.rep.dashboard",
            "get_dashboard_stats",
            [],
            {
                date_from: this.state.date_from,
                date_to: this.state.date_to,
                sales_rep_id: this.state.sales_rep_id ? parseInt(this.state.sales_rep_id) : false,
            }
        );
        this.state.data = result;
    }

    renderCharts() {
        this.destroyCharts();

        // 1. Route Completion Donut Chart
        if (this.routeChartRef.el) {
            const ctx = this.routeChartRef.el.getContext("2d");
            const data = this.state.data.route_status_data;
            this.routeChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: data.map(d => d.status.charAt(0).toUpperCase() + d.status.slice(1)),
                    datasets: [{
                        data: data.map(d => d.count),
                        backgroundColor: ['#1e3a5f', '#2d7a8d', '#17a2b8', '#1e7e34', '#ffc107'],
                        borderWidth: 0,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, padding: 20 } }
                    },
                    cutout: '70%'
                }
            });
        }

        // 2. Visit Completion Stacked Bar Chart
        if (this.visitChartRef.el) {
            const ctx = this.visitChartRef.el.getContext("2d");
            const data = this.state.data.daily_visit_data;
            this.visitChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: data.map(d => d.date),
                    datasets: [
                        {
                            label: 'Completed',
                            data: data.map(d => d.completed),
                            backgroundColor: '#1e3a5f',
                        },
                        {
                            label: 'Pending',
                            data: data.map(d => d.pending),
                            backgroundColor: '#2d7a8d',
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { stacked: true, grid: { display: false } },
                        y: { stacked: true, beginAtZero: true }
                    },
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12 } }
                    }
                }
            });
        }

        // 3. Efficiency Gauge (Semi-circle)
        if (this.efficiencyGaugeRef.el) {
            const ctx = this.efficiencyGaugeRef.el.getContext("2d");
            const val = this.state.data.kpis.efficiency;
            this.efficiencyGauge = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    datasets: [{
                        data: [val, 100 - val],
                        backgroundColor: ['#28a745', '#e2e8f0'],
                        borderWidth: 0,
                    }]
                },
                options: {
                    rotation: 270,
                    circumference: 180,
                    cutout: '80%',
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                    maintainAspectRatio: false,
                }
            });
        }
    }

    destroyCharts() {
        if (this.routeChart) this.routeChart.destroy();
        if (this.visitChart) this.visitChart.destroy();
        if (this.efficiencyGauge) this.efficiencyGauge.destroy();
    }

    formatCurrency(value) {
        return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    async openAction(resModel) {
        let name = resModel.split('.').pop().charAt(0).toUpperCase() + resModel.split('.').pop().slice(1) + 's';
        let dateField = 'date';
        
        if (resModel === 'sales.rep.collection' || resModel === 'account.payment') {
            name = 'Payments';
            dateField = (resModel === 'sales.rep.collection') ? 'collection_date' : 'date';
        } else if (resModel === 'sales.rep.visit') {
            dateField = 'route_id.date';
        } else if (resModel === 'sale.order') {
            dateField = 'date_order';
        }

        let domain = [[dateField, '>=', this.state.date_from], [dateField, '<=', this.state.date_to]];
        
        if (this.state.sales_rep_id) {
            domain.push(['sales_rep_id', '=', parseInt(this.state.sales_rep_id)]);
        }

        await this.action.doAction({
            type: 'ir.actions.act_window',
            name: name,
            res_model: resModel,
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            target: 'current',
        });
    }
}

SalesRepDashboard.template = "sales_rep_dashboard_template";

registry.category("actions").add("sales_rep_dashboard", SalesRepDashboard);