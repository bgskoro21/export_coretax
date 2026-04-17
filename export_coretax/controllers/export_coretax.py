from odoo import http
from odoo.http import request
from odoo.modules import get_module_path
import os

class EfakturDownload(http.Controller):

    @http.route('/export_coretax/download/coretax', type='http', auth="user")
    def download_coretax(self, filename=None, **kw):
        # Jika tidak ada filename yang dikirim, gunakan default lama (opsional)
        if not filename:
            filename = 'tax_invoice_bulk_ok.xml'
            
        module_path = get_module_path('export_coretax')
        file_path = os.path.join(module_path, 'static', filename)

        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Headers ini yang menentukan nama file saat muncul di browser
            headers = [
                ('Content-Type', 'application/xml'),
                ('Content-Disposition', 'attachment; filename=%s' % filename),
            ]
            return request.make_response(data, headers=headers)
        else:
            return "File tidak ditemukan."