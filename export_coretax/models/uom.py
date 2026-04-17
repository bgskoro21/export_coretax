# -*- coding: utf-8 -*-
from odoo import models, fields

class UomUom(models.Model):
    # Gunakan 'product.uom' jika Anda di Odoo versi 11 ke bawah
    _inherit = 'product.uom' 

    l10n_id_coretax_uom_code = fields.Char(string='Coretax UOM Code', default="UM.0024", help="Kode Satuan Ukur resmi untuk Coretax/E-Faktur 4.0")