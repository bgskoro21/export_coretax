# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError
import time
import os
import xml.etree.ElementTree as ET
from odoo.tools.float_utils import float_round


# =============================================================================
# MODEL BARIS FAKTUR
# =============================================================================

class ExportCoretaxInvoiceLine(models.TransientModel):
    _name = 'export_coretax.invoice.line'
    _description = 'Baris Faktur Export Coretax'

    wizard_id = fields.Many2one(
        'export_coretax.export_efaktur',
        string='Wizard',
        required=True,
        ondelete='cascade',
    )
    invoice_id = fields.Many2one(
        'account.invoice',
        string='Faktur',
        required=True,
    )
    selected = fields.Boolean(string='Export?', default=True)
    billing_period = fields.Date(
        string='Periode Tagihan',
        help='Ubah periode ini jika faktur ingin ditagihkan di bulan lain.',
    )

    # ── Tampilan read-only dari invoice ──────────────────────────────────────
    number      = fields.Char(related='invoice_id.number',        string='No. Faktur',  readonly=True)
    partner_id  = fields.Many2one('res.partner', related='invoice_id.partner_id', string='Customer', readonly=True)
    date_invoice= fields.Date(related='invoice_id.date_invoice',  string='Tgl. Faktur', readonly=True)
    amount_untaxed = fields.Monetary(related='invoice_id.amount_untaxed', string='AMOUNT UNTAXED',   readonly=True)
    amount_tax     = fields.Monetary(related='invoice_id.amount_tax',     string='PPN',   readonly=True)
    amount_total   = fields.Monetary(related='invoice_id.amount_total',   string='Total', readonly=True)
    currency_id    = fields.Many2one('res.currency', related='invoice_id.currency_id', readonly=True)
    state          = fields.Selection(related='invoice_id.state', string='Status', readonly=True)


# =============================================================================
# WIZARD UTAMA
# =============================================================================

class ExportCoretaxWizard(models.TransientModel):
    _name = 'export_coretax.export_efaktur'
    _description = 'Export Faktur Pajak Coretax'

    date_from  = fields.Date(string='Dari Tanggal')
    date_to    = fields.Date(string='Sampai Tanggal')
    partner_id = fields.Many2one('res.partner', string='Customer', domain=[('customer', '=', True)])

    invoice_line_ids = fields.One2many(
        'export_coretax.invoice.line', 'wizard_id',
        string='Faktur Siap Export',
    )
    exported_invoice_ids = fields.Many2many(
        'account.invoice',
        'export_coretax_exported_rel', 'wizard_id', 'invoice_id',
        string='Faktur Sudah Diexport',
    )

    # ── Helper: kembalikan ke form dalam EDIT MODE ────────────────────────────
    def _reopen_form(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'flags': {'initial_mode': 'edit'},   # ← KUNCI: paksa edit mode
        }

    # =========================================================================
    # ACTIONS
    # =========================================================================

    @api.multi
    def action_search(self):
        # Auto-simpan billing_period yang sudah diubah user sebelum mencari ulang
        for line in self.invoice_line_ids:
            if line.billing_period and line.invoice_id:
                line.invoice_id.write({'coretax_billing_period': line.billing_period})

        base_domain = [
            ('state', 'in', ['open', 'paid']),
            ('type', '=', 'out_invoice'),
            ('is_coretax_exported', '=', False),
            ('tax_line_ids.tax_id.amount', '!=', 0),
        ]
        exported_domain = [
            ('type', '=', 'out_invoice'),
            ('is_coretax_exported', '=', True),
            ('tax_line_ids.tax_id.amount', '!=', 0),
        ]

        if self.partner_id:
            base_domain.append(('partner_id', '=', self.partner_id.id))
            exported_domain.append(('partner_id', '=', self.partner_id.id))

        if self.date_from or self.date_to:
            domain_no_bp   = list(base_domain)   + [('coretax_billing_period', '=', False)]
            domain_with_bp = list(base_domain)   + [('coretax_billing_period', '!=', False)]
            exp_no_bp      = list(exported_domain) + [('coretax_billing_period', '=', False)]
            exp_with_bp    = list(exported_domain) + [('coretax_billing_period', '!=', False)]

            if self.date_from:
                domain_no_bp.append(('date_invoice', '>=', self.date_from))
                domain_with_bp.append(('coretax_billing_period', '>=', self.date_from))
                exp_no_bp.append(('date_invoice', '>=', self.date_from))
                exp_with_bp.append(('coretax_billing_period', '>=', self.date_from))
            if self.date_to:
                domain_no_bp.append(('date_invoice', '<=', self.date_to))
                domain_with_bp.append(('coretax_billing_period', '<=', self.date_to))
                exp_no_bp.append(('date_invoice', '<=', self.date_to))
                exp_with_bp.append(('coretax_billing_period', '<=', self.date_to))

            inv_no_bp  = self.env['account.invoice'].search(domain_no_bp)
            inv_with_bp= self.env['account.invoice'].search(domain_with_bp)
            invoices   = (inv_no_bp | inv_with_bp).sorted(key=lambda r: r.date_invoice or '')

            exp_a = self.env['account.invoice'].search(exp_no_bp)
            exp_b = self.env['account.invoice'].search(exp_with_bp)
            exported = (exp_a | exp_b).sorted(key=lambda r: r.date_invoice or '')
        else:
            invoices = self.env['account.invoice'].search(base_domain, order='date_invoice asc')
            exported = self.env['account.invoice'].search(exported_domain, order='date_invoice asc')

        # Isi baris
        self.invoice_line_ids = [(5, 0, 0)]
        lines = []
        for inv in invoices:
            lines.append((0, 0, {
                'invoice_id': inv.id,
                'selected': True,
                'billing_period': inv.coretax_billing_period or inv.date_invoice,
            }))
        self.invoice_line_ids = lines
        self.exported_invoice_ids = [(6, 0, exported.ids)]

        return self._reopen_form()

    @api.multi
    def action_save_billing_periods(self):
        if not self.invoice_line_ids:
            raise UserError("Tidak ada faktur. Lakukan pencarian dulu.")
        for line in self.invoice_line_ids:
            if line.billing_period:
                line.invoice_id.write({'coretax_billing_period': line.billing_period})
        return self.action_search()
    

    @api.multi
    def action_select_all(self):
        if not self.invoice_line_ids:
            raise UserError("Tidak ada faktur. Lakukan pencarian dulu.")
        self.invoice_line_ids.write({'selected': True})
        return self._reopen_form()

    @api.multi
    def action_unselect_all(self):
        if not self.invoice_line_ids:
            raise UserError("Tidak ada faktur. Lakukan pencarian dulu.")
        self.invoice_line_ids.write({'selected': False})
        return self._reopen_form()

    @api.multi
    def action_export(self):
        selected_lines = self.invoice_line_ids.filtered(lambda l: l.selected)
        if not selected_lines:
            raise UserError("Centang minimal satu faktur yang ingin diexport.")

        company = self.env.user.company_id.partner_id
        npwp_seller = (company.npwp.replace('.', '').replace('-', '').strip()
                       if company.npwp else '')
        seller_idtku = npwp_seller + '000000'

        root = ET.Element('TaxInvoiceBulk')
        root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        root.set('xsi:noNamespaceSchemaLocation', 'TaxInvoice.xsd')
        ET.SubElement(root, 'TIN').text = npwp_seller
        list_of_tax_invoice = ET.SubElement(root, 'ListOfTaxInvoice')

        exported_ids = []
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        for line in selected_lines:
            inv = line.invoice_id
            if line.billing_period:
                inv.write({'coretax_billing_period': line.billing_period})
            self._append_tax_invoice_xml(list_of_tax_invoice, inv, seller_idtku)
            self.env.cr.execute(
                "UPDATE account_invoice SET is_coretax_exported=True, date_coretax_exported=%s WHERE id=%s",
                (now_str, inv.id),
            )
            exported_ids.append(inv.id)

        today_str = fields.Date.today()
        filename  = "XML-PPN-%s.xml" % today_str
        module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path   = os.path.join(module_path, 'static', filename)

        self._indent_xml(root)
        ET.ElementTree(root).write(file_path, encoding='utf-8', xml_declaration=True)

        selected_lines.unlink()
        self.write({'exported_invoice_ids': [(4, i) for i in exported_ids]})
        self.env.cr.commit()

        return {
            'type': 'ir.actions.act_url',
            'url': '/export_coretax/download/coretax?filename=%s' % filename,
            'target': 'self',
        }

    @api.multi
    def action_open_reset_wizard(self):
        if not self.exported_invoice_ids:
            raise UserError("Tidak ada faktur yang sudah diexport.")
        reset_wizard = self.env['export_coretax.reset.wizard'].create({
            'parent_wizard_id': self.id,
            'line_ids': [
                (0, 0, {'invoice_id': inv.id, 'selected': False})
                for inv in self.exported_invoice_ids
            ],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pilih Faktur untuk Direset',
            'res_model': 'export_coretax.reset.wizard',
            'res_id': reset_wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # =========================================================================
    # XML HELPERS
    # =========================================================================

    def _append_tax_invoice_xml(self, parent, inv, seller_idtku):
        partner    = inv.partner_id
        buyer_type = partner.buyer_id_type or 'tin'
        npwp_buyer = (partner.npwp or '').replace('.', '').replace('-', '').strip()

        if buyer_type == 'national':
            val_buyer_tin = '0000000000000000'
            val_buyer_doc = 'National ID'
            val_buyer_doc_number = partner.national_id or npwp_buyer
            val_buyer_idtku = npwp_buyer + '000000'
        elif buyer_type == 'other':
            val_buyer_tin = '0000000000000000'
            val_buyer_doc = 'Other ID'
            val_buyer_doc_number = inv.number or ''
            val_buyer_idtku = '0000000000000000'
        else:
            val_buyer_tin = npwp_buyer
            val_buyer_doc = 'TIN'
            val_buyer_doc_number = ''
            val_buyer_idtku = (partner.spesific_nitku
                               if partner.is_spesific_nitku and partner.spesific_nitku
                               else npwp_buyer + '000000')

        tax_invoice = ET.SubElement(parent, 'TaxInvoice')
        ET.SubElement(tax_invoice, 'TaxInvoiceDate').text    = inv.coretax_billing_period or inv.date_invoice
        ET.SubElement(tax_invoice, 'TaxInvoiceOpt').text     = 'Normal'
        ET.SubElement(tax_invoice, 'TrxCode').text           = '04'
        ET.SubElement(tax_invoice, 'AddInfo')
        ET.SubElement(tax_invoice, 'CustomDoc')
        ET.SubElement(tax_invoice, 'RefDesc').text           = inv.number or ''
        ET.SubElement(tax_invoice, 'FacilityStamp')
        ET.SubElement(tax_invoice, 'SellerIDTKU').text       = seller_idtku
        ET.SubElement(tax_invoice, 'BuyerTin').text          = val_buyer_tin
        ET.SubElement(tax_invoice, 'BuyerDocument').text     = val_buyer_doc
        ET.SubElement(tax_invoice, 'BuyerCountry').text      = 'IDN'
        ET.SubElement(tax_invoice, 'BuyerDocumentNumber').text = val_buyer_doc_number
        ET.SubElement(tax_invoice, 'BuyerName').text         = partner.name or ''
        ET.SubElement(tax_invoice, 'BuyerAdress').text       = partner.alamat_lengkap or ''
        ET.SubElement(tax_invoice, 'BuyerEmail').text        = partner.email or ''
        ET.SubElement(tax_invoice, 'BuyerIDTKU').text        = val_buyer_idtku

        list_of_good_service = ET.SubElement(tax_invoice, 'ListOfGoodService')
        for line in inv.invoice_line_ids:
            self._append_good_service_xml(list_of_good_service, line)

    def _append_good_service_xml(self, parent, line):
        price_unit = line.price_unit or 0.0
        quantity   = line.quantity   or 0.0
        discount   = line.discount   or 0.0
        first_subtotal = price_unit * quantity

        price_after_discount = price_unit * (1 - discount / 100.0)
        price    = float_round(price_after_discount / 1.11, 2)
        subtotal = price * quantity

        tax_rate       = sum(tax.amount for tax in line.invoice_line_tax_ids)
        tax_base       = float_round(subtotal, 2)
        total_discount = float_round(price_unit * quantity * (discount / 100.0), 2)
        other_tax_base = float_round(tax_base * 11.0 / 12.0, 2)
        vat            = float_round(first_subtotal - tax_base, 2)
        uom_code       = line.uom_id.l10n_id_coretax_uom_code or 'UM.0033'

        gs = ET.SubElement(parent, 'GoodService')
        ET.SubElement(gs, 'Opt').text          = 'B'
        ET.SubElement(gs, 'Code').text         = '120100'
        ET.SubElement(gs, 'Name').text         = line.product_id.name or ''
        ET.SubElement(gs, 'Unit').text         = uom_code
        ET.SubElement(gs, 'Price').text        = '%.2f' % price
        ET.SubElement(gs, 'Qty').text          = '%.2f' % quantity
        ET.SubElement(gs, 'TotalDiscount').text= '%.2f' % total_discount
        ET.SubElement(gs, 'TaxBase').text      = '%.2f' % tax_base
        ET.SubElement(gs, 'OtherTaxBase').text = '%.2f' % other_tax_base
        ET.SubElement(gs, 'VATRate').text      = '12'
        ET.SubElement(gs, 'VAT').text          = '%.2f' % vat
        ET.SubElement(gs, 'STLGRate').text     = '0'
        ET.SubElement(gs, 'STLG').text         = '0'

    def _indent_xml(self, elem, level=0):
        indent = '\n' + '  ' * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + '  '
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            for child in elem:
                self._indent_xml(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent
        if not level:
            elem.tail = '\n'
