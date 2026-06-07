"""
HTML Report Generator
Orchestrator yang merakit semua section menjadi satu file HTML.
"""

import os
from datetime import datetime

from core.reporter.section_inventory import generate_services_inventory
from core.reporter.section_summary   import generate_summary_services
from core.reporter.section_cost      import generate_cost_optimization


def generate_html_report(assessment_data: dict, customer_name: str,
                         account_id: str, region: str) -> str:
    """Generate HTML report dari template dan kembalikan path file output."""
    print("\n📄 Generating HTML report...")

    # ── Load template ─────────────────────────────────────────────────────────
    template_path = 'templates/report_template.html'
    if not os.path.exists(template_path):
        template_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'templates', 'report_template.html'
        )
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # ── Load static assets ────────────────────────────────────────────────────
    def _load_asset(rel_path: str) -> str:
        if os.path.exists(rel_path):
            with open(rel_path, 'r', encoding='utf-8') as f:
                return f.read()
        fallback = os.path.join(
            os.path.dirname(__file__), '..', '..', rel_path
        )
        if os.path.exists(fallback):
            with open(fallback, 'r', encoding='utf-8') as f:
                return f.read()
        return ''

    report_styles  = _load_asset('templates/report_styles.css')
    report_scripts = _load_asset('templates/report_scripts.js')

    # ── Summary numbers ───────────────────────────────────────────────────────
    total_services  = len([k for k, v in assessment_data['services'].items()
                           if v.get('count', 0) > 0])
    total_resources = sum(v.get('count', 0) for v in assessment_data['services'].values())

    total_monthly_cost = 0
    billing = assessment_data.get('billing_data', {})
    if billing and 'monthly_costs' in billing and billing['monthly_costs']:
        total_monthly_cost = billing['monthly_costs'][-1]['total']

    # ── Basic placeholder replacements ────────────────────────────────────────
    replacements = {
        '{{CUSTOMER_NAME}}':       customer_name,
        '{{ACCOUNT_ID}}':          account_id,
        '{{ASSESSMENT_DATE}}':     datetime.now().strftime('%d %B %Y'),
        '{{AWS_REGION}}':          region,
        '{{SERVICES_COUNT}}':      str(total_services),
        '{{RESOURCES_COUNT}}':     str(total_resources),
        '{{TOTAL_MONTHLY_COST}}':  f'${total_monthly_cost:,.2f}' if total_monthly_cost > 0 else '$0.00',
        '{{GENERATION_TIMESTAMP}}': datetime.now().strftime('%d %B %Y, %H:%M:%S'),
        '/* __REPORT_STYLES__ */': report_styles,
        '/* __REPORT_SCRIPTS__ */': report_scripts,
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    # ── Top Cost Drivers ──────────────────────────────────────────────────────
    if billing and 'top_services' in billing:
        top_drivers_html = ''.join(
            f'''<tr>
                    <td>{svc}</td>
                    <td>${cost:,.2f}</td>
                    <td>{(cost / total_monthly_cost * 100) if total_monthly_cost > 0 else 0:.1f}%</td>
                </tr>'''
            for svc, cost in billing['top_services'][:10]
        )
    else:
        top_drivers_html = (
            '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">'
            'Data billing tidak tersedia.</td></tr>'
        )
    template = template.replace('{{TOP_COST_DRIVERS}}', top_drivers_html)

    # ── Sections ──────────────────────────────────────────────────────────────
    template = template.replace('{{SUMMARY_SERVICES}}',         generate_summary_services(assessment_data))
    template = template.replace('{{SERVICES_INVENTORY_CONTENT}}', generate_services_inventory(assessment_data))
    template = template.replace('{{COST_OPTIMIZATION}}',        generate_cost_optimization(assessment_data))

    # ── Save ──────────────────────────────────────────────────────────────────
    os.makedirs('output', exist_ok=True)
    timestamp   = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'output/assessment_report_{timestamp}.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(template)

    print(f"✓ HTML report generated: {output_file}")
    return output_file
