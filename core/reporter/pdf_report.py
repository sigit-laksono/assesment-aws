"""
PDF Report Generator
Render HTML report ke PDF menggunakan Playwright headless Chromium.
"""

import os
from datetime import datetime


def generate_pdf_report(html_file: str) -> str | None:
    """Generate PDF dari file HTML. Return path PDF atau None jika gagal."""
    print("\n📄 Generating PDF report...")

    try:
        from playwright.sync_api import sync_playwright

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_file  = f'output/assessment_report_{timestamp}.pdf'
        abs_html_path = f'file://{os.path.abspath(html_file)}'

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page    = browser.new_page()
            page.goto(abs_html_path)

            print("  - Waiting for content to render...")
            page.wait_for_timeout(2000)

            print("  - Disabling pagination and filters for PDF...")
            page.evaluate("""
                document.querySelectorAll('tr').forEach(tr => {
                    tr.classList.remove('page-hidden');
                    tr.classList.remove('filtered-hidden');
                });
                document.querySelectorAll('.table-wrapper, .service-detail-card, h3').forEach(el => {
                    el.classList.remove('filtered-hidden');
                });
            """)

            page.pdf(
                path=pdf_file,
                format='A4',
                print_background=True,
                margin={'top': '1cm', 'right': '1cm', 'bottom': '1cm', 'left': '1cm'},
                display_header_footer=True,
                header_template=(
                    '<div style="font-size:10px;width:100%;text-align:center;color:#666;">'
                    'AWS Account Assessment Report</div>'
                ),
                footer_template=(
                    '<div style="font-size:10px;width:100%;text-align:center;color:#666;">'
                    'Page <span class="pageNumber"></span> / <span class="totalPages"></span></div>'
                ),
            )
            browser.close()

        print(f"✓ PDF report generated: {pdf_file}")
        return pdf_file

    except ImportError:
        print("⚠ playwright tidak terinstall. Jalankan:")
        print("  pip install playwright && playwright install chromium")
        return None
    except Exception as e:
        print(f"✗ Error generating PDF: {str(e)}")
        return None
