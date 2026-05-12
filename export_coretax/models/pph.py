# -*- coding: utf-8 -*-
from odoo import api, models


class PphWizardInherit(models.TransientModel):
    _inherit = 'mhs.pph'

    # =========================================================================
    # HELPER: cari invoice dengan dukungan coretax_billing_period
    # =========================================================================

    def _search_invoices_with_period(self, base_domain, start, end):
        """
        Cari invoice dengan mempertimbangkan coretax_billing_period.
        - Invoice TANPA billing_period → filter pakai date_invoice
        - Invoice DENGAN billing_period → filter pakai coretax_billing_period
        Hasil digabung dan dikembalikan sebagai recordset.
        """
        inv_obj = self.env['account.invoice']

        domain_no_bp = list(base_domain) + [
            ('coretax_billing_period', '=', False),
            ('date_invoice', '>=', start),
            ('date_invoice', '<=', end),
        ]
        print("DOmain")
        domain_with_bp = list(base_domain) + [
            ('coretax_billing_period', '!=', False),
            ('coretax_billing_period', '>=', start),
            ('coretax_billing_period', '<=', end),
        ]

        inv_no_bp   = inv_obj.search(domain_no_bp)
        inv_with_bp = inv_obj.search(domain_with_bp)

        return (inv_no_bp | inv_with_bp).sorted(key=lambda r: r.date_invoice or '')

    # =========================================================================
    # OVERRIDE: find_invoices
    # =========================================================================

    @api.multi
    def find_invoices(self):
        start = self.start
        end   = self.end
        invoice_ids = []

        if self.status == 'open':
            base = [('state', '=', 'open'), ('type', '=', 'out_invoice')]
            invoices = self._search_invoices_with_period(base, start, end)
            invoice_ids = [(4, inv.id) for inv in invoices]

        elif self.status == 'paid':
            # Paid tetap pakai payment_date, tapi filter lambda tidak pakai efaktur_id
            payment_obj = self.env['account.payment']
            payments = payment_obj.search([
                ('payment_date', '>=', start),
                ('payment_date', '<=', end),
            ])
            for payment in payments:
                for invoice in payment.invoice_ids.filtered(
                    lambda s: s.state == 'paid' and s.type == 'out_invoice'
                ):
                    invoice_ids.append((4, invoice.id))

        elif self.status == 'openpaid':
            base_open = [('state', '=', 'open'), ('type', '=', 'out_invoice')]
            base_paid = [('state', '=', 'paid'), ('type', '=', 'out_invoice')]
            inv_open  = self._search_invoices_with_period(base_open, start, end)
            inv_paid  = self._search_invoices_with_period(base_paid, start, end)
            invoice_ids = [(4, inv.id) for inv in (inv_open | inv_paid)]

        self.invoice_ids = invoice_ids
        self.env.cr.commit()

    # =========================================================================
    # OVERRIDE: print_pajak_v2
    # =========================================================================

    @api.multi
    def print_pajak_v2(self):
        import csv, base64, pytz, datetime
        from odoo.modules import get_module_path
        from odoo.exceptions import UserError

        start   = self.start
        end     = self.end
        no_skip = self.exclude_tenant_tax

        headers = [
            'NO', 'BANK', 'NAMA', 'No KIOS', 'KETERANGAN', 'PERIODE',
            'DPP', 'PPN', 'TOTAL', 'BANK MASUK',
            'PPH Ps 4 Di Byr Simpur', 'PPH Ps 4 Di Byr Tenant',
            'PPH 4 (420) 0,5%', 'FAKTUR PAJAK', 'REFERENSI', 'NPWP',
            'PAYMENT DATE', 'INVOICE DATE',
        ]

        csv_path  = get_module_path('mhs_efaktur') + '/static/rekap_pajak.csv'
        csvfile   = open(csv_path, 'wb')
        csvwriter = csv.writer(csvfile, delimiter=',')
        csvwriter.writerow([h.upper() for h in headers])
        no = 0

        if self.status == 'open':
            base = [
                ('state',        '=', 'open'),
                ('type',         '=', 'out_invoice'),
                ('tenant_taxed', '=', no_skip),
            ]
            invoices = self._search_invoices_with_period(base, start, end)
            self.invoice_ids = [(6, 0, invoices.ids)]
            for invoice in invoices:
                no += 1
                self.baris_data(headers, csvwriter, invoice, no, False)

        elif self.status == 'paid':
            payment_obj = self.env['account.payment']
            payments    = payment_obj.search([
                ('payment_date', '>=', start),
                ('payment_date', '<=', end),
            ])
            invoices_paid = payments.mapped('invoice_ids').filtered(
                lambda inv: inv.state == 'paid' and inv.type == 'out_invoice'
            )
            self.invoice_ids = [(6, 0, invoices_paid.ids)]
            for payment in payments:
                for invoice in payment.invoice_ids.filtered(
                    lambda inv: inv.state == 'paid' and inv.type == 'out_invoice'
                ):
                    no += 1
                    self.baris_data(headers, csvwriter, invoice, no, payment)

        else:  # openpaid
            base_open = [
                ('state',        '=', 'open'),
                ('type',         '=', 'out_invoice'),
                ('tenant_taxed', '=', no_skip),
            ]
            base_paid = [
                ('state',        '=', 'paid'),
                ('type',         '=', 'out_invoice'),
                ('tenant_taxed', '=', no_skip),
            ]
            inv_open = self._search_invoices_with_period(base_open, start, end)
            inv_paid = self._search_invoices_with_period(base_paid, start, end)

            self.invoice_ids = [(6, 0, (inv_open | inv_paid).ids)]

            for invoice in inv_open:
                no += 1
                self.baris_data(headers, csvwriter, invoice, no, False)

            for invoice in inv_paid:
                no += 1
                payment = invoice.payment_ids[0] if invoice.payment_ids else False
                self.baris_data(headers, csvwriter, invoice, no, payment)

        tgl = datetime.datetime.now()
        self.date_rekap = tgl
        csvfile.close()

        tmpfile     = open(csv_path, 'rb')
        jkt_tz      = pytz.timezone("Asia/Jakarta")
        current_tgl = pytz.utc.localize(tgl).astimezone(jkt_tz).strftime('%y-%m-%d-%H-%M-%S')
        self.efaktur_filename = 'RekapBaru_' + current_tgl + '.csv'
        self.efaktur_file     = base64.b64encode(tmpfile.read())
        tmpfile.close()

        self.env.cr.commit()

        if self.invoice_ids:
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        else:
            raise UserError("Penarikan Data Kosong!")