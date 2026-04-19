# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.modules import get_module_path
import time
import os
import xml.etree.ElementTree as ET
from odoo.tools.float_utils import float_round


class ExportCoretaxWizard(models.TransientModel):
    _name = 'export_coretax.export_efaktur'
    _description = 'Export Faktur Pajak Coretax'

    # =====================
    # FILTER FIELDS
    # =====================
    date_from = fields.Date(string='Dari Tanggal')
    date_to = fields.Date(string='Sampai Tanggal')
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        domain=[('customer', '=', True)]
    )

    # =====================
    # RESULT FIELDS
    # =====================
    invoice_ids = fields.Many2many(
        'account.invoice',
        'export_coretax_invoice_rel',
        'wizard_id',
        'invoice_id',
        string='Faktur Siap Export',
    )

    exported_invoice_ids = fields.Many2many(
        'account.invoice',
        'export_coretax_exported_rel',
        'wizard_id',
        'invoice_id',
        string='Faktur Sudah Diexport',
    )

    # =====================
    # ACTIONS
    # =====================

    @api.multi
    def action_search(self):
        """Cari faktur berdasarkan filter yang diisi."""

        # Domain untuk faktur belum di-export
        domain = [
            ('state', 'in', ['open', 'paid']),   # ← ganti = ke in
            ('type', '=', 'out_invoice'),
            ('is_coretax_exported', '=', False),
            ('tax_line_ids.tax_id.amount', '!=', 0),
        ]

        # Domain untuk faktur sudah di-export
        exported_domain = [
            ('type', '=', 'out_invoice'),
            ('is_coretax_exported', '=', True),
            ('tax_line_ids.tax_id.amount', '!=', 0),  # ← tambah ini juga
        ]

        # Terapkan filter tanggal
        if self.date_from:
            domain.append(('date_invoice', '>=', self.date_from))
            exported_domain.append(('date_invoice', '>=', self.date_from))
        if self.date_to:
            domain.append(('date_invoice', '<=', self.date_to))
            exported_domain.append(('date_invoice', '<=', self.date_to))

        # Terapkan filter customer
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
            exported_domain.append(('partner_id', '=', self.partner_id.id))

        invoices = self.env['account.invoice'].search(domain, order='date_invoice asc')
        exported = self.env['account.invoice'].search(exported_domain, order='date_invoice asc')

        self.invoice_ids = [(6, 0, invoices.ids)]
        self.exported_invoice_ids = [(6, 0, exported.ids)]

        # Populate checkbox lines dari exported
        self.reset_line_ids = [(5, 0, 0)]
        self.reset_line_ids = [
            (0, 0, {'invoice_id': inv.id, 'selected': False})
            for inv in exported
        ]

        # Re-open form dengan data terbaru
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.multi
    def action_export(self):
        """Export faktur yang ada di invoice_ids ke XML Coretax."""
        invoices = self.invoice_ids

        if not invoices:
            raise UserError("Tidak ada faktur untuk diexport.")

        company = self.env.user.company_id.partner_id
        npwp_seller = company.npwp.replace('.', '').replace('-', '').strip() if company.npwp else ''
        seller_idtku = npwp_seller + '000000'

        root = ET.Element('TaxInvoiceBulk')
        root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        root.set('xsi:noNamespaceSchemaLocation', 'TaxInvoice.xsd')

        ET.SubElement(root, 'TIN').text = npwp_seller
        list_of_tax_invoice = ET.SubElement(root, 'ListOfTaxInvoice')

        for inv in self.invoice_ids:
            # Simpan status aslinya dulu
            old_state = inv.state 
            
            self._append_tax_invoice_xml(list_of_tax_invoice, inv, seller_idtku)
            
            # Update field e-faktur saja
            query = """
                UPDATE account_invoice 
                SET is_coretax_exported = True, 
                    date_coretax_exported = %s 
                WHERE id = %s
            """
            self.env.cr.execute(query, (time.strftime("%Y-%m-%d %H:%M:%S"), inv.id))

        # --- PERUBAHAN NAMA FILE DI SINI ---
        today_str = fields.Date.today() # Mengambil tanggal hari ini (YYYY-MM-DD)
        filename = "XML-PPN-%s.xml" % today_str
        
        module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        file_path = os.path.join(module_path, 'static', filename)
        # ----------------------------------

        self._indent_xml(root)
        tree = ET.ElementTree(root)
        tree.write(file_path, encoding='utf-8', xml_declaration=True)

        self.write({
            'invoice_ids': [(5, 0, 0)],               # kosongkan tab siap export
            'exported_invoice_ids': [                  # tambahkan ke tab sudah diexport
                (4, inv_id) for inv_id in invoices.ids
            ],
        })

        self.env.cr.commit()

        # Pastikan controller download Anda menerima parameter nama file 
        # atau sesuaikan URL-nya agar bisa mengunduh file yang baru saja dibuat
        return {
            'type': 'ir.actions.act_url',
            'url': '/export_coretax/download/coretax?filename=%s' % filename,
            'target': 'self',
        }

    @api.multi
    def action_reset_exported(self):
        selected_lines = self.reset_line_ids.filtered(lambda l: l.selected)

        if not selected_lines:
            raise UserError("Centang minimal satu faktur yang ingin direset.")

        selected_invoices = selected_lines.mapped('invoice_id')

        selected_invoices.write({
            'is_coretax_exported': False,
            'date_coretax_exported': False,
        })

        self.write({
            'invoice_ids': [(4, inv.id) for inv in selected_invoices],
            'exported_invoice_ids': [(3, inv.id) for inv in selected_invoices],
        })

        selected_lines.unlink()
        self.env.cr.commit()

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('export_coretax.view_export_coretax_form').id,
            'target': 'current',
        }
    
    @api.multi
    def action_open_reset_wizard(self):
        if not self.exported_invoice_ids:
            raise UserError("Tidak ada faktur yang sudah diexport.")

        # Buat reset wizard dengan lines dari exported invoices
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
            'target': 'new',  # popup!
        }

    # =====================
    # XML HELPERS
    # =====================

    def _append_tax_invoice_xml(self, parent, inv, seller_idtku):
        partner = inv.partner_id
        
        buyer_type = partner.buyer_id_type or 'tin' 
        npwp_buyer = (partner.npwp or '').replace('.', '').replace('-', '').strip()

        if buyer_type == 'national':
            val_buyer_tin = '0000000000000000'
            val_buyer_doc = 'National ID'
            val_buyer_doc_number = (partner.national_id or npwp_buyer)
            val_buyer_idtku = npwp_buyer + '000000'

        elif buyer_type == 'other':
            val_buyer_tin = '0000000000000000'
            val_buyer_doc = 'Other ID'
            val_buyer_doc_number = inv.number or ''
            val_buyer_idtku = '0000000000000000'
            
        else:  # Default TIN (NPWP)
            val_buyer_tin = npwp_buyer
            val_buyer_doc = 'TIN'
            val_buyer_doc_number = ''
            if partner.is_spesific_nitku and partner.spesific_nitku:
                val_buyer_idtku = partner.spesific_nitku
            else:
                val_buyer_idtku = npwp_buyer + '000000'

        tax_invoice = ET.SubElement(parent, 'TaxInvoice')

        ET.SubElement(tax_invoice, 'TaxInvoiceDate').text = inv.date_invoice or ''
        ET.SubElement(tax_invoice, 'TaxInvoiceOpt').text = 'Normal'
        ET.SubElement(tax_invoice, 'TrxCode').text = '04'
        ET.SubElement(tax_invoice, 'AddInfo')
        ET.SubElement(tax_invoice, 'CustomDoc')
        ET.SubElement(tax_invoice, 'RefDesc').text = inv.number or ''
        ET.SubElement(tax_invoice, 'FacilityStamp')
        ET.SubElement(tax_invoice, 'SellerIDTKU').text = seller_idtku

        ET.SubElement(tax_invoice, 'BuyerTin').text = val_buyer_tin
        ET.SubElement(tax_invoice, 'BuyerDocument').text = val_buyer_doc
        ET.SubElement(tax_invoice, 'BuyerCountry').text = 'IDN'
        ET.SubElement(tax_invoice, 'BuyerDocumentNumber').text = val_buyer_doc_number
        ET.SubElement(tax_invoice, 'BuyerName').text = partner.name or ''
        ET.SubElement(tax_invoice, 'BuyerAdress').text = partner.alamat_lengkap or ''
        ET.SubElement(tax_invoice, 'BuyerEmail').text = partner.email or '-'
        ET.SubElement(tax_invoice, 'BuyerIDTKU').text = val_buyer_idtku

        list_of_good_service = ET.SubElement(tax_invoice, 'ListOfGoodService')
        for line in inv.invoice_line_ids:
            self._append_good_service_xml(list_of_good_service, line)

    def _append_good_service_xml(self, parent, line):
        price_unit = line.price_unit or 0.0
        quantity = line.quantity or 0.0
        discount = line.discount or 0.0

        price_after_discount = price_unit * (1 - discount / 100.0)
        price = float_round(price_after_discount / 1.11, 2)
        subtotal = price * quantity

        # Ambil rate dari tax yang ada di line
        tax_rate = sum(tax.amount for tax in line.invoice_line_tax_ids)

        # DPP per line = subtotal / 1.11
        tax_base = float_round(subtotal, 2)
        total_discount = float_round(price_unit * quantity * (discount / 100.0), 2)
        other_tax_base = tax_base

        # VAT dari rate tax line yang sebenarnya
        vat = float_round(tax_base * (tax_rate / 100.0), 2)

        uom_code = line.uom_id.l10n_id_coretax_uom_code or 'UM.0001'

        good_service = ET.SubElement(parent, 'GoodService')
        ET.SubElement(good_service, 'Opt').text = 'B'
        ET.SubElement(good_service, 'Code').text = ''
        ET.SubElement(good_service, 'Name').text = line.product_id.name or ''
        ET.SubElement(good_service, 'Unit').text = uom_code
        ET.SubElement(good_service, 'Price').text = '%.2f' % price_unit
        ET.SubElement(good_service, 'Qty').text = str(int(quantity))
        ET.SubElement(good_service, 'TotalDiscount').text = '%.2f' % total_discount
        ET.SubElement(good_service, 'TaxBase').text = '%.2f' % tax_base
        ET.SubElement(good_service, 'OtherTaxBase').text = '%.2f' % other_tax_base
        ET.SubElement(good_service, 'VATRate').text = '12'
        ET.SubElement(good_service, 'VAT').text = '%.2f' % vat
        ET.SubElement(good_service, 'STLGRate').text = '0'
        ET.SubElement(good_service, 'STLG').text = '0'

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