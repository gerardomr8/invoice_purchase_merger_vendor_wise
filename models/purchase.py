from odoo import api, fields, models, _
from odoo.tools.mail import append_content_to_html
from reportlab.lib import geomutils
from odoo.api import multi
from passlib.tests.utils import limit
from odoo.exceptions import UserError, RedirectWarning, ValidationError
# from odoo.tools.yaml_tag import record_constructor
from datetime import date

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"
    _description = "Purchase Merger"
    
    @api.depends('order_line.invoice_lines.invoice_id')
    def _compute_invoice(self):
        for order in self:
            invoices = self.env['account.invoice']
            for line in order.order_line:
                invoices |= line.invoice_lines.mapped('invoice_id')
                order.invoice_ids = invoices
                order.invoice_count = len(invoices)
                order.invoice_count = len(self.env['account.invoice'].search([('origin', 'like', order.name)]))
    
    @api.multi
    def action_view_invoice(self):
        '''
        This function returns an action that display existing vendor bills of given purchase order ids.
        When only one found, show the vendor bill immediately.
        '''
        action = self.env.ref('account.action_invoice_tree2')
        result = action.read()[0]

        # override the context to get rid of the default filtering
        result['context'] = {'type': 'in_invoice', 'default_purchase_id': self.id}
        if self.invoice_count == 0:
            if not self.invoice_ids:
                # Choose a default account journal in the same currency in case a new invoice is created
                journal_domain = [
                    ('type', '=', 'purchase'),
                    ('company_id', '=', self.company_id.id),
                    ('currency_id', '=', self.currency_id.id),
                ]
                default_journal_id = self.env['account.journal'].search(journal_domain, limit=1)
                if default_journal_id:
                    result['context']['default_journal_id'] = default_journal_id.id
            else:
                # Use the same account journal than a previous invoice
                result['context']['default_journal_id'] = self.invoice_ids[0].journal_id.id
    
            # choose the view_mode accordingly
            if len(self.invoice_ids) != 1:
                result['domain'] = "[('id', 'in', " + str(self.invoice_ids.ids) + ")]"
            elif len(self.invoice_ids) == 1:
                res = self.env.ref('account.invoice_supplier_form', False)
                result['views'] = [(res and res.id or False, 'form')]
                result['res_id'] = self.invoice_ids.id
 
        else: 
            if self.invoice_count <=1: 
                inv_reference = self.env['account.invoice'].search([('origin', 'like', self.name)]) 
                form_view = self.env.ref('account.invoice_supplier_form').id
                tree_view = self.env.ref('account.invoice_supplier_tree').id            
                return{
                            'name': _('Invoice'),
                            'type':'ir.actions.act_window',
                            'view_type':'form',
                            'view_mode':'form,tree',
                            'res_model':'account.invoice',
                            'res_id':inv_reference.id,
                            'views_id':True,
                            'views':[ (form_view , 'form'), (tree_view , 'tree')],
                            'domain':[('origin', 'like', self.name)],
                            'target': 'current',
                                                            }
            else:       
                form_view = self.env.ref('account.invoice_supplier_form').id
                tree_view = self.env.ref('account.invoice_supplier_tree').id            
                return{
                                                'name': _('Invoice'),
                                                'type':'ir.actions.act_window',
                                                'view_type':'form',
                                                'view_mode':'form,tree',
                                                'res_model':'account.invoice',
                                                'views_id':True,
                                                'views':[(tree_view , 'tree'), (form_view , 'form')],
                                                'domain':[('origin', 'like', self.name)],
                                                'target': 'current',
                                                            }      
            
        return result  
                                                      
    @api.multi
    def merge_purchase_invoice(self):  
        """"To Merge Two Or More Purchase Order With One Partner Id That Can Be Merge As Single File To Create a Invoice """
        active_id = self.env['purchase.order'].browse(self.env['purchase.order']._context.get('active_ids'))
        journal_id = self.env['account.journal'].search([('type', '=', 'purchase')]) 
        active_id_count = 0
        active_count = 0
        exist_vendor = []; invoice = [];exist_vendors = [];ctx = ();invoice_id = []
        for rec in active_id :  
            po_reference = self.env['account.invoice'].search([('origin', 'like', rec.name)])
            active_count = len(active_id)
            if  rec.picking_count >= 1 and rec.picking_count != rec.invoice_count:
                len_name = []       
                for inv in po_reference:      
                    len_name = inv.origin.split(":")     
                if rec.name in len_name:
                    if po_reference.state == 'draft':
                        for record in po_reference.invoice_line_ids:
                            print (record.line_id)
                            for res in rec.order_line:
                                if res.id == record.line_id:   
                                    record.write({'quantity':res.qty_received})
                                    res.write({'qty_invoiced':record.quantity})
                                        
                    else:
                           
                            po_list = [];line_values = {};lines = {};purchase = []
                            if rec.state in 'purchase' and rec.invoice_status in 'to invoice':
                                purchase.append(rec.id)
                                active_id_count = len(purchase)
                                if rec.partner_id.id in exist_vendor:
                                    for inv in invoice:
                                        if inv['partner_id'] == rec.partner_id.id:
                                            for recc in rec.order_line:
                                                if rec.picking_count > 1 and rec.invoice_count >= 1:
                                                    qty_received = recc.qty_received - recc.qty_invoiced 
                                                else:
                                                    qty_received = recc.qty_received    
                                                line_values = (0, 0, {'product_id': recc.product_id.id,
                                                'quantity': qty_received ,
                                                'price_unit': recc.price_unit,
                                                'invoice_line_tax_ids': [(6, 0, recc.taxes_id and recc.taxes_id.ids) or False] ,
                                                'price_subtotal': recc.price_subtotal,
                                                'product_uom': recc.product_uom.id,
                                                'name': recc.name,
                                                'account_id': journal_id.default_debit_account_id.id ,
                                                'line_id':recc.id
                                                })             
                                                inv['invoice_line_ids'].append(line_values)
                                            inv['origin'] = inv['origin'] + ':' + rec.name
                                    if rec.partner_id.id not in exist_vendor:
                                        exist_vendors.append(rec.partner_id.id)     
                                else: 
                                    for recc in rec.order_line:
                                        if rec.picking_count > 1 and rec.invoice_count >= 1:
                                                    qty_received = recc.qty_received - recc.qty_invoiced 
                                        else:
                                                    qty_received = recc.qty_received
                                        line_values = (0, 0, {'product_id': recc.product_id.id,
                                                     'quantity': qty_received,
                                                     'price_unit': recc.price_unit,
                                                    'invoice_line_tax_ids': [(6, 0, recc.taxes_id and recc.taxes_id.ids)or False],
                                                     'price_subtotal': recc.price_subtotal,
                                                     'product_uom': recc.product_uom.id,
                                                     'name': recc.name,
                                                    'account_id': journal_id.default_debit_account_id.id,
                                                    'line_id':recc.id
                                                     }) 
                                        print (rec.id)
                                        po_list.append(line_values)     
                                    invoice.append({'origin':rec.name, 'partner_id': rec.partner_id.id, 'invoice_line_ids':po_list, 'account_id': rec.partner_id.property_account_payable_id.id, 'type': 'in_invoice', 'journal_id':journal_id.id,'date_invoice':datetime.today()})      
                                    if rec.partner_id.id not in exist_vendor:
                                        exist_vendor.append(rec.partner_id.id)    
                                        
                else:
                            po_list = [];line_values = {};lines = {};purchase = []
                            if rec.state in 'purchase' and rec.invoice_status in 'to invoice':
                                purchase.append(rec.id)
                                active_id_count = len(purchase)
                                if rec.partner_id.id in exist_vendor:
                                    for inv in invoice:
                                        if inv['partner_id'] == rec.partner_id.id:
                                            for recc in rec.order_line:
                                                if rec.picking_count > 1 and rec.invoice_count >= 1:
                                                    qty_received = recc.qty_received - recc.qty_invoiced 
                                                else:
                                                    qty_received = recc.qty_received
                                                line_values = (0, 0, {'product_id': recc.product_id.id,
                                                'quantity': qty_received ,
                                                'price_unit': recc.price_unit,
                                                'invoice_line_tax_ids': [(6, 0, recc.taxes_id and recc.taxes_id.ids) or False] ,
                                                'price_subtotal': recc.price_subtotal,
                                                'product_uom': recc.product_uom.id,
                                                'name': recc.name,
                                                'account_id': journal_id.default_debit_account_id.id ,
                                                'line_id':recc.id
                                                })             
                                                inv['invoice_line_ids'].append(line_values)
                                            inv['origin'] = inv['origin'] + ':' + rec.name
                                    if rec.partner_id.id not in exist_vendor:
                                        exist_vendors.append(rec.partner_id.id)     
                                else: 
                                    for recc in rec.order_line:
                                        if rec.picking_count > 1 and rec.invoice_count >= 1:
                                                    qty_received = recc.qty_received - recc.qty_invoiced 
                                        else:
                                                    qty_received = recc.qty_received
                                        line_values = (0, 0, {'product_id': recc.product_id.id,
                                                     'quantity': qty_received,
                                                     'price_unit': recc.price_unit,
                                                    'invoice_line_tax_ids': [(6, 0, recc.taxes_id and recc.taxes_id.ids)or False],
                                                     'price_subtotal': recc.price_subtotal,
                                                     'product_uom': recc.product_uom.id,
                                                     'name': recc.name,
                                                    'account_id': journal_id.default_debit_account_id.id,
                                                    'line_id':recc.id
                                                     }) 
                                        print (rec.id)
                                        po_list.append(line_values)   
                                    invoice.append({'origin':rec.name, 'partner_id': rec.partner_id.id, 'invoice_line_ids':po_list, 'account_id': rec.partner_id.property_account_payable_id.id, 'type': 'in_invoice', 'journal_id':journal_id.id,'date_invoice':date.today()})   
                                    if rec.partner_id.id not in exist_vendor:
                                        exist_vendor.append(rec.partner_id.id)             
                                                                             
        invoices = []
        invoice_counts = 0
        for record in invoice:
            invoice_id = self.env['account.invoice'].create(record)
            invoices.append(invoice_id.id)
        invoice_counts = len(invoices)
        if active_id_count == 1:
            if invoice_counts == 1:
                form_view = self.env.ref('purchase.view_invoice_supplier_purchase_form').id
                tree_view = self.env.ref('account.invoice_tree').id            
                return{
                                        'name': _('Invoice'),
                                        'type':'ir.actions.act_window',
                                        'view_type':'form',
                                        'view_mode':'form,tree',
                                        'res_model':'account.invoice',
                                        'res_id':invoices[0],
                                        'views_id':False,
                                        'views':[(form_view , 'form'), (tree_view , 'tree')],
                                        'domain':[('id', 'in', invoices)],
                                        'target': 'current',
                                             }     
            else:     
                form_view = self.env.ref('account.invoice_supplier_form').id
                tree_view = self.env.ref('account.invoice_supplier_tree').id            
                return{
                                        'name': _('Invoice'),
                                        'type':'ir.actions.act_window',
                                        'view_type':'form',
                                        'view_mode':'form,tree',
                                        'res_model':'account.invoice',
                                        'views_id':True,
                                        'views':[(tree_view , 'tree'), (form_view , 'form')],
                                        'domain':[('id', 'in', invoices)],
                                        'target': 'current',
                                                    }  
             
class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    purchase_count = fields.Integer("Count", compute='compute_pruchase_order')    
            
    @api.model
    def create(self, vals):
        count = []
        invoice = super(AccountInvoice, self).create(vals)
        purchase = invoice.invoice_line_ids.mapped('purchase_line_id.order_id')
        if purchase and not invoice.refund_invoice_id:
            message = _("This vendor bill has been created from: %s") % (",".join(["<a href=# data-oe-model=purchase.order data-oe-id=" + str(order.id) + ">" + order.name + "</a>" for order in purchase]))
            invoice.message_post(body=message)   
        qty_invoiced = 0.00;
        for record in vals.get('invoice_line_ids'):
            if record[2]:   
                qty_invoiced = record[2]['quantity']
                purchase_line_id = self.env['purchase.order.line'].search([('id', '=', record[2]['line_id'])])
                purchase_line_id.write({'qty_invoiced':purchase_line_id.qty_invoiced + qty_invoiced})
            else:   
                purchase_line_id.write({'qty_invoiced':purchase_line_id.qty_invoiced + qty_invoiced})
        len_name = []       
        for rec in invoice:      
            len_name = rec.origin.split(':')                                        
        purchase_id = self.env['purchase.order'].search([('name','in',len_name)])
        
        count = len(purchase_id)
        for res in purchase_id:
            invoice_id = self.env['account.invoice'].search([('origin','like',res.name)])
            inv_count = len(invoice_id)
            if inv_count == 0:
                res.write({'invoice_count':count})
            else:
                res.write({'invoice_count':inv_count})
        return invoice    
    
    @api.multi
    def write(self, vals):       
        result = True
        for invoice in self:
            purchase_old = invoice.invoice_line_ids.mapped('purchase_line_id.order_id')
            result = result and super(AccountInvoice, invoice).write(vals)
            purchase_new = invoice.invoice_line_ids.mapped('purchase_line_id.order_id')
            # To get all po reference when updating invoice line or adding purchase order reference from vendor bill.
            purchase = (purchase_old | purchase_new) - (purchase_old & purchase_new)
            if purchase:
                message = _("This vendor bill has been modified from: %s") % (",".join(["<a href=# data-oe-model=purchase.order data-oe-id=" + str(order.id) + ">" + order.name + "</a>" for order in purchase]))
                invoice.message_post(body=message)                                            
        return result
 
    @api.multi
    def compute_pruchase_order(self):
        len_name = []       
        for rec in self:      
            len_name = rec.origin.split(':')                                        
            self.purchase_count = len(self.env['purchase.order'].search([('name', '=', len_name)]))
   
    @api.multi
    def purchase_order(self):    
        len_name = []       
        for rec in self:      
            len_name = rec.origin.split(':') 
           
        if self.purchase_count == 1:
            purchase_count = self.env['purchase.order'].search([('name', '=', len_name)])
            form_view = self.env.ref('purchase.purchase_order_form').id
            tree_view = self.env.ref('purchase.purchase_order_tree').id
            return{
                      'name': _('Purchase Order'),
                      'type':'ir.actions.act_window',
                      'view_type':'form',
                      'view_mode':'form,tree',
                      'res_id':purchase_count.id,
                      'res_model':'purchase.order',
                      'views_id':False,
                      'views':[(form_view , 'form'), (tree_view , 'tree')],
                      'domain':[('name', '=', len_name)]
                      
                      }       
                    
        else:
            form_view = self.env.ref('purchase.purchase_order_form').id
            tree_view = self.env.ref('purchase.purchase_order_tree').id
            return{
                      'name': _('Purchase Order'),
                      'type':'ir.actions.act_window',
                      'view_type':'form',
                      'view_mode':'form,tree',
                      'res_model':'purchase.order',
                      'views_id':False,
                      'views':[(tree_view , 'tree'), (form_view , 'form')],
                      'domain':[('name', '=', len_name)]
                      
                      }       

class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line' 
      
    line_id = fields.Integer("line id")

