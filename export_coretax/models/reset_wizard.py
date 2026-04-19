# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError

class CoretaxResetLine(models.TransientModel):
    _name = 'export_coretax.reset.line'

    wizard_id = fields.Many2one('export_coretax.reset.wizard')
    invoice_id = fields.Many2one('account.invoice')
    selected = fields.Boolean(string='Reset?', default=False)
    number = fields.Char(related='invoice_id.number', string='No. Faktur', readonly=True)
    partner_id = fields.Many2one(related='invoice_id.partner_id', string='Customer', readonly=True)
    date_invoice = fields.Date(related='invoice_id.date_invoice', string='Tgl. Faktur', readonly=True)
    date_coretax_exported = fields.Datetime(related='invoice_id.date_coretax_exported', string='Tgl. Export', readonly=True)
    amount_total = fields.Monetary(related='invoice_id.amount_total', string='Total', readonly=True)
    currency_id = fields.Many2one(related='invoice_id.currency_id', readonly=True)


class CoretaxResetWizard(models.TransientModel):
    _name = 'export_coretax.reset.wizard'

    parent_wizard_id = fields.Integer(string='Parent Wizard ID')
    line_ids = fields.One2many('export_coretax.reset.line', 'wizard_id', string='Faktur')

    @api.multi
    def action_select_all(self):
        self.line_ids.write({'selected': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.multi
    def action_unselect_all(self):
        self.line_ids.write({'selected': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.multi
    def action_reset(self):
        selected_lines = self.line_ids.filtered(lambda l: l.selected)

        if not selected_lines:
            raise UserError("Centang minimal satu faktur yang ingin direset.")

        selected_invoices = selected_lines.mapped('invoice_id')

        selected_invoices.write({
            'is_coretax_exported': False,
            'date_coretax_exported': False,
        })

        parent = self.env['export_coretax.export_efaktur'].browse(self.parent_wizard_id)
        if parent.exists():
            parent.write({
                'invoice_ids': [(4, inv.id) for inv in selected_invoices],
                'exported_invoice_ids': [(3, inv.id) for inv in selected_invoices],
            })
            parent.env.cr.commit()

        return {'type': 'ir.actions.act_window_close'}