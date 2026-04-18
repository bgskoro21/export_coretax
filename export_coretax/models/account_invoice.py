# -*- coding: utf-8 -*-
from odoo import models, api, fields
import xml.etree.ElementTree as ET
import base64
from io import BytesIO

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
    coretax_reset_selected = fields.Boolean(string='Reset?', default=False, copy=False)
