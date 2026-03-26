# -*- coding: utf-8 -*-
from odoo import models, fields, api,_


class Project(models.Model):
    _inherit = 'project.project'

    def action_project_project_sharing(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('spd_portal_project_view.open_view_project_all_inherit')
        action['context'] = {
            'default_project_id': self.id,
            'delete': False,
            'search_default_open_tasks': True,
            'active_id_chatter': self.id,
        }
        return action
