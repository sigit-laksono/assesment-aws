"""
Section: Cost Optimization
Render tabel findings dari collectors/cost_optimization.py.
"""


def generate_cost_optimization(assessment_data: dict) -> str:
    """Generate HTML untuk Cost Optimization section."""
    co       = assessment_data.get('cost_optimization', {})
    findings = co.get('findings', [])
    summary  = co.get('summary', {})
    total    = co.get('total_potential_savings', 0)
    note     = co.get('price_region_note', '')

    if not findings:
        return '''
        <div style="padding:32px;text-align:center;background:#f8fafc;border-radius:8px;
                    border:1px dashed #cbd5e1;">
            <p style="color:#64748b;">✅ Tidak ditemukan waste yang jelas dari rule yang dievaluasi.</p>
        </div>'''

    # Summary cards per kategori
    cards_html = ''.join(
        f'''<div class="stat-item">
                <div class="stat-label">{cat}</div>
                <div class="stat-value">{data['count']}</div>
                <div style="font-size:0.8em;color:#ef4444;margin-top:2px;">~${data['savings']:.2f}/bln</div>
            </div>'''
        for cat, data in summary.items()
    )

    # Tabel detail findings
    sev_colors = {'high': '#dc2626', 'medium': '#f59e0b', 'low': '#6b7280'}
    rows_html = ''.join(
        f'''<tr>
                <td><span style="color:{sev_colors.get(f.get('severity','medium'),'#6b7280')};
                         font-weight:600;text-transform:uppercase;font-size:0.75em">
                    {f.get('severity','medium')}</span></td>
                <td>{f['category']}</td>
                <td><code style="font-size:0.85em">{f['resource_id']}</code></td>
                <td style="color:#64748b;font-size:0.9em">{f['details']}</td>
                <td style="color:#ef4444;font-weight:600;white-space:nowrap">
                    ~${f['estimated_monthly_cost']:.2f}/bln</td>
                <td style="font-size:0.85em;color:#475569">{f.get('action','-')}</td>
            </tr>'''
        for f in findings
    )

    return f'''
    <div class="service-detail-card" style="border-left:4px solid #f59e0b;">
        <div class="service-summary-stats">
            <div class="stat-item">
                <div class="stat-label">💰 Total Potential Savings</div>
                <div class="stat-value" style="color:#f59e0b">~${total:.2f}</div>
                <div style="font-size:0.8em;color:#64748b;margin-top:2px;">per bulan</div>
            </div>
            {cards_html}
        </div>
        <div class="table-wrapper" style="margin-top:16px">
            <table>
                <thead>
                    <tr>
                        <th>Severity</th><th>Kategori</th><th>Resource</th>
                        <th>Detail</th><th>Est. Cost/Bulan</th><th>Recommended Action</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
        <p style="margin-top:12px;font-size:0.8em;color:#94a3b8">⚠ {note}</p>
    </div>'''
