from odoo import api, fields, models, _

class ResPartner(models.Model):
    _inherit = 'res.partner'

    buyer_id_type = fields.Selection(
        string=_('ID Pembeli'),
        selection=[
            ('npwp', 'NPWP'),
            ('national', 'National ID'),
            ('other', 'Other'),
        ],
        default="other"
    )

    specific_nitku = fields.Char(string='NITKU Cabang')

    is_spesific_nitku = fields.Boolean(string=_('Perlu NITKU Cabang?'), default=False)
    
    