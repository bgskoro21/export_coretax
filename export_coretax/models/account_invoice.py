# -*- coding: utf-8 -*-
from odoo import models, api, fields


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    is_coretax_exported = fields.Boolean(
        string='Sudah Diexport Coretax',
        default=False,
        copy=False,
    )
    date_coretax_exported = fields.Datetime(
        string='Tanggal Export Coretax',
        readonly=True,
        copy=False,
    )
    coretax_reset_selected = fields.Boolean(
        string='Reset?',
        default=False,
        copy=False,
    )
    coretax_billing_period = fields.Date(
        string='Periode Tagihan Coretax',
        copy=False,
        help=(
            'Periode penagihan khusus untuk Coretax. '
            'Jika diisi, faktur ini akan muncul saat filter periode yang sesuai '
            'meskipun tanggal fakturnya berbeda.'
        ),
    )