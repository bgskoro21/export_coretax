# -*- coding: utf-8 -*-
{
    'name': "Export Coretax",
    'summary': "Module to export dummy Pajak Keluaran (e-Faktur) in XML format",
    'description': """
        This module provides a button in the Invoice form to export
        dummy XML files for Pajak Keluaran (Output Tax). 
        Useful for testing XML generation and download functionality in Odoo 10.
    """,
    'author': "Bagaskara",
    'website': "http://www.yourcompany.com",
    'category': 'Accounting',
    'version': '0.1',
    'depends': ['base', 'account', 'mhs_efaktur'],
    'data': [
        'wizards/pk_coretax_views.xml',
        'views/export_coretax_views.xml',
        'views/res_partner_views.xml',
        'views/uom_views.xml',
        'views/menu.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': True,
}
