# -*- coding: utf-8 -*-
#################################################################################
# Author      : Zero For Information Systems (<www.erpzero.com>)
# Copyright(c): 2016-Zero For Information Systems
# All Rights Reserved.
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################


from . import models


def pre_init_check(cr):
    from odoo.service import common
    from odoo.exceptions import UserError
    version_info = common.exp_version()
    server_serie =version_info.get('server_serie')
    if server_serie!='18.0':raise UserError('Module support Odoo series 18.0 found {}.'.format(server_serie))
    return True


def _configure_journals(env):
    # if we already have a coa installed, create journal and set property field
    for company in env['res.company'].search([('chart_template', '!=', False)]):
        ChartTemplate = env['account.chart.template'].with_company(company)
        template_code = company.chart_template
        template_data = ChartTemplate._get_chart_template_data(template_code)['template_data']
        if 'property_stock_account_indirect_cost_id' in template_data:
            data = {'property_stock_account_indirect_cost_id': template_data['property_stock_account_indirect_cost_id']}
            ChartTemplate._post_load_data(template_code, company, data)
