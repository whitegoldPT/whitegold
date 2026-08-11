from odoo import models, fields, api
import io
import xlsxwriter
import base64
from datetime import datetime

class TraccarReportWizard(models.TransientModel):
    _name = 'traccar.report.wizard'
    _description = 'Traccar Reports Wizard'

    report_type = fields.Selection([
        ('device_summary', 'Device Summary'),
        ('position_history', 'Position History'),
        ('travel_report', 'Travel Report'),
        ('stop_report', 'Stop Report')
    ], string='Report Type', required=True, default='device_summary')
    
    device_ids = fields.Many2many('traccar.device', string='Devices')
    from_date = fields.Datetime(string='From Date', required=True)
    to_date = fields.Datetime(string='To Date', required=True)
    export_format = fields.Selection([
        ('xlsx', 'Excel'),
        ('pdf', 'PDF')
    ], string='Export Format', default='xlsx')

    def generate_report(self):
        """Generate the selected report"""
        if self.export_format == 'xlsx':
            return self._generate_excel_report()
        else:
            return self._generate_pdf_report()

    def _generate_pdf_report(self):
        """Generate PDF report"""
        return self.env.ref('traccar_integration.action_traccar_pdf_report').report_action(self)

    def _generate_excel_report(self):
        """Generate Excel report"""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        
        if self.report_type == 'device_summary':
            self._create_device_summary_sheet(workbook)
        elif self.report_type == 'position_history':
            self._create_position_history_sheet(workbook)
        
        workbook.close()
        output.seek(0)
        
        # Create attachment
        filename = f"traccar_{self.report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _create_device_summary_sheet(self, workbook):
        """Create device summary sheet"""
        worksheet = workbook.add_worksheet('Device Summary')
        
        # Headers
        headers = ['Device Name', 'Unique ID', 'Status', 'Last Position', 
                  'Total Positions', 'Avg Speed (km/h)', 'Max Speed (km/h)']
        
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3'})
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Data
        devices = self.device_ids if self.device_ids else self.env['traccar.device'].search([('unique_id', '!=', 'DASHBOARD_ONLY')])
        
        for row, device in enumerate(devices, 1):
            positions = device.position_ids.filtered(
                lambda p: self.from_date <= p.device_time <= self.to_date
            )
            
            worksheet.write(row, 0, device.name)
            worksheet.write(row, 1, device.unique_id)
            worksheet.write(row, 2, device.status)
            worksheet.write(row, 3, device.last_update.strftime('%Y-%m-%d %H:%M') if device.last_update else '')
            worksheet.write(row, 4, len(positions))
            worksheet.write(row, 5, sum(positions.mapped('speed_kmh')) / len(positions) if positions else 0)
            worksheet.write(row, 6, max(positions.mapped('speed_kmh')) if positions else 0)

    def _create_position_history_sheet(self, workbook):
        """Create position history sheet"""
        worksheet = workbook.add_worksheet('Position History')
        
        # Headers
        headers = ['Device', 'Time', 'Latitude', 'Longitude', 'Speed (km/h)', 
                  'Course', 'Altitude', 'Valid']
        
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3'})
        
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Data
        domain = [
            ('device_time', '>=', self.from_date),
            ('device_time', '<=', self.to_date)
        ]
        if self.device_ids:
            domain.append(('device_id', 'in', self.device_ids.ids))
        
        positions = self.env['traccar.position'].search(domain, order='device_time desc')
        
        for row, position in enumerate(positions, 1):
            worksheet.write(row, 0, position.device_id.name)
            worksheet.write(row, 1, position.device_time.strftime('%Y-%m-%d %H:%M:%S'))
            worksheet.write(row, 2, position.latitude)
            worksheet.write(row, 3, position.longitude)
            worksheet.write(row, 4, position.speed_kmh)
            worksheet.write(row, 5, position.course or 0)
            worksheet.write(row, 6, position.altitude or 0)
            worksheet.write(row, 7, 'Yes' if position.valid else 'No')