from odoo import models, fields, api, tools

class AssetStockMovementReport(models.Model):
    _name = 'asset.stock.movement.report'
    _description = 'Asset Stock Movement Analysis'
    _auto = False
    _order = 'date desc'

    asset_id = fields.Many2one('asset.management', string='Asset', readonly=True)
    asset_name = fields.Char(string='Asset Name', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    movement_type = fields.Selection([
        ('assign', 'Assigned'),
        ('return', 'Returned')
    ], string='Movement Type', readonly=True)
    user_id = fields.Many2one('res.users', string='Done By', readonly=True)
    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    t.id,
                    t.asset_id,
                    a.name as asset_name,
                    t.transfer_employee_id as employee_id,
                    t.assign_date as date,
                    'assign' as movement_type,
                    t.assign_by as user_id
                FROM
                    asset_transfer_entry t
                JOIN
                    asset_management a ON t.asset_id = a.id
                WHERE
                    a.model_type = 'multiple'
                UNION ALL
                SELECT
                    t.id + 100000,
                    t.asset_id,
                    a.name as asset_name,
                    t.transfer_employee_id as employee_id,
                    t.return_date as date,
                    'return' as movement_type,
                    t.assign_by as user_id
                FROM
                    asset_transfer_entry t
                JOIN
                    asset_management a ON t.asset_id = a.id
                WHERE
                    a.model_type = 'multiple'
                    AND t.return_date IS NOT NULL
            )
        """ % self._table)