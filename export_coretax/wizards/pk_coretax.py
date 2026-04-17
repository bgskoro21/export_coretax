# -*- coding: utf-8 -*-
import base64
import calendar
import datetime
import os
import pytz
import xml.etree.ElementTree as ET

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.modules import get_module_path

ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'


class pph_coretax_inherit(models.TransientModel):
    _inherit = 'mhs.pph'

    bpu_file = fields.Binary(attachment=True, readonly=True)
    bpu_filename = fields.Char(string="BPU FileName")

    # ------------------------------------------------------------------
    # Helper: hitung DPP & PPh 4(2) per invoice
    # ------------------------------------------------------------------
    def _count_pph4(self, inv):
        dpp = int(inv.amount_untaxed)
        pph = 0
        for line in inv.invoice_line_ids:
            if self.exclude_tenant_tax:
                pph += int(line.price_subtotal_pph4_company or 0)
            else:
                pph += int(
                    (line.price_subtotal_pph4_company or 0)
                    + (line.price_subtotal_pph4_tenant or 0)
                )
        return dpp, pph

    # ------------------------------------------------------------------
    # Helper: kumpulkan invoice sesuai filter
    # ------------------------------------------------------------------
    def _get_invoices_pph4(self):
        inv_obj = self.env['account.invoice']
        start, end = self.start, self.end
        base_domain = [
            ('date_invoice', '>=', start),
            ('date_invoice', '<=', end),
            ('is_efaktur_exported', '!=', False),
            ('type', '=', 'out_invoice'),
        ]

        if self.status == 'open':
            return inv_obj.search(base_domain + [('state', '=', 'open')], limit=1)

        elif self.status == 'paid':
            payment_obj = self.env['account.payment']
            payments = payment_obj.search([
                ('payment_date', '>=', start),
                ('payment_date', '<=', end),
            ])
            invoice_ids = set()
            for payment in payments:
                for inv in payment.invoice_ids.filtered(
                    lambda s: s.state == 'paid'
                    and s.type == 'out_invoice'
                    and s.is_efaktur_exported
                ):
                    invoice_ids.add(inv.id)
            return inv_obj.browse(list(invoice_ids))

        else:  # openpaid
            open_inv = inv_obj.search(base_domain + [('state', '=', 'open')])
            paid_inv = inv_obj.search(base_domain + [('state', '=', 'paid')])
            return open_inv | paid_inv

    # ------------------------------------------------------------------
    # Helper: build satu elemen <Bpu>
    # ------------------------------------------------------------------
    def _build_bpu_element(self, parent, inv, place_of_business):
        buyer_id_type = getattr(inv.partner_id, 'buyer_id_type', False)

        if buyer_id_type == 'other':
            # Untuk tipe "other": CounterpartTin & IDPlaceOfBusiness diisi nol
            npwp_buyer  = '0000000000000000'        # 16 digit
            buyer_idtku = '0000000000000000000000'  # 22 digit
        else:
            if not inv.partner_id.npwp:
                raise UserError(
                    "NPWP customer belum diisi: %s" % inv.partner_id.name
                )
            npwp_buyer  = inv.partner_id.npwp.replace('.', '').replace('-', '')
            buyer_idtku = npwp_buyer + '000000'     # 22 digit

        dpp, pph = self._count_pph4(inv)

        rate = 0.5  # default PPh 4(2) sewa tanah/bangunan

        d = datetime.datetime.strptime(inv.date_invoice, '%Y-%m-%d')
        month = d.month
        year  = d.year
        last_day = calendar.monthrange(year, month)[1]
        withholding_date = '%s-%02d-%02d' % (year, month, last_day)

        doc_number = inv.number or 'CMS.001'

        bpu = ET.SubElement(parent, 'Bpu')

        ET.SubElement(bpu, 'TaxPeriodMonth').text = str(month)
        ET.SubElement(bpu, 'TaxPeriodYear').text  = str(year)
        ET.SubElement(bpu, 'CounterpartTin').text  = npwp_buyer
        ET.SubElement(bpu, 'IDPlaceOfBusinessActivityOfIncomeRecipient').text = buyer_idtku

        ET.SubElement(bpu, 'TaxCertificate').text = getattr(inv, 'pph4_tax_certificate', 'N/A') or 'N/A'
        ET.SubElement(bpu, 'TaxObjectCode').text  = getattr(inv, 'pph4_object_code', '22-101-02') or '22-101-02'

        ET.SubElement(bpu, 'TaxBase').text = str(dpp)
        ET.SubElement(bpu, 'Rate').text    = str(rate)

        ET.SubElement(bpu, 'Document').text       = 'CommercialInvoice'
        ET.SubElement(bpu, 'DocumentNumber').text = doc_number or '-'
        ET.SubElement(bpu, 'DocumentDate').text   = inv.date_invoice or ''
        ET.SubElement(bpu, 'IDPlaceOfBusinessActivity').text = place_of_business
        ET.SubElement(bpu, 'GovTreasurerOpt').text = 'N/A'

        sp2d = ET.SubElement(bpu, 'SP2DNumber')
        sp2d.set('{%s}nil' % XSI_NS, 'true')

        ET.SubElement(bpu, 'WithholdingDate').text = withholding_date

    # ------------------------------------------------------------------
    # Helper: pretty print XML
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # Main button
    # ------------------------------------------------------------------
    @api.multi
    def export_xml(self):
        # 1. Cari invoice berdasarkan filter (start, end, status)
        invoices = self._get_invoices_pph4()

        if not invoices:
            raise UserError(
                "Tidak ada invoice yang ditemukan untuk periode %s s/d %s."
                % (self.start, self.end)
            )

        # 2. SET INVOICE KE FIELD Many2many (invoice_ids)
        # Kita gunakan (6, 0, [ids]) untuk mereplace isi Many2many dengan hasil pencarian terbaru
        self.invoice_ids = [(6, 0, invoices.ids)]

        # --- Mulai Proses Pembuatan XML ---
        company = self.env.user.company_id.partner_id
        npwp_company = company.npwp.replace('.', '').replace('-', '') if company.npwp else ''
        place_of_business = npwp_company + '000000'

        root = ET.Element('BpuBulk')
        ET.SubElement(root, 'TIN').text = npwp_company
        list_of_bpu = ET.SubElement(root, 'ListOfBpu')

        for inv in invoices:
            self._build_bpu_element(list_of_bpu, inv, place_of_business)

        self._indent_xml(root)
        tree = ET.ElementTree(root)

        module_path = get_module_path('export_coretax')
        file_path = os.path.join(module_path, 'static', 'pph4_bpu_bulk.xml')
        tree.write(file_path, encoding='utf-8', xml_declaration=True)

        with open(file_path, 'rb') as f:
            content = f.read()

        jkt_tz = pytz.timezone('Asia/Jakarta')
        now_jkt = pytz.utc.localize(datetime.datetime.utcnow()).astimezone(jkt_tz)
        tgl_str = now_jkt.strftime('%y-%m-%d-%H-%M-%S')

        # Set hasil file ke field binary agar muncul link download-nya
        self.bpu_filename = 'PPh4_BpuBulk_%s.xml' % tgl_str
        self.bpu_file = base64.b64encode(content)

        # Commit agar data tersimpan sebelum reload
        self.env.cr.commit()

        # Reload page agar field invoice_ids dan link download file muncul di layar
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }