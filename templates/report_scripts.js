/**
 * Logika Pemetaan Kategori
 */
function getServiceCategory(serviceName) {
    const name = serviceName.toLowerCase();
    if (name.includes('ec2') || name.includes('eks') || name.includes('ecs') || name.includes('lambda') || name.includes('compute')) return 'compute';
    if (name.includes('s3') || name.includes('ebs') || name.includes('efs') || name.includes('backup') || name.includes('storage')) return 'storage';
    if (name.includes('rds') || name.includes('elasticache') || name.includes('dynamodb') || name.includes('aurora') || name.includes('database')) return 'database';
    if (name.includes('vpc') || name.includes('elb') || name.includes('alb') || name.includes('nlb') || name.includes('nat') || name.includes('cloudfront') || name.includes('route 53') || name.includes('networking')) return 'networking';
    if (name.includes('waf') || name.includes('kms') || name.includes('iam') || name.includes('shield') || name.includes('secrets') || name.includes('security')) return 'security';
    if (name.includes('cloudwatch') || name.includes('cloudtrail') || name.includes('config') || name.includes('management')) return 'management';
    if (name.includes('msk') || name.includes('mq') || name.includes('sns') || name.includes('sqs') || name.includes('integration')) return 'integration';
    if (name.includes('glue') || name.includes('athena') || name.includes('kinesis') || name.includes('analytics')) return 'analytics';
    if (name.includes('sagemaker') || name.includes('bedrock') || name.includes('ml') || name.includes('machine learning')) return 'ml';
    if (name.includes('codecommit') || name.includes('codebuild') || name.includes('codepipeline') || name.includes('devtools')) return 'devtools';
    if (name.includes('dms') || name.includes('datasync') || name.includes('migration')) return 'migration';
    if (name.includes('cost') || name.includes('budget')) return 'cost';
    return 'other';
}

/**
 * Membangun Menu Sidebar Secara Dinamis
 */
function buildDynamicMenu() {
    const inventory = document.getElementById('services-inventory');
    const subNav = document.getElementById('dynamic-sub-nav');
    const headers = inventory.querySelectorAll('h3');
    subNav.innerHTML = '';

    headers.forEach((h3, index) => {
        const id = h3.id || 'svc-' + index;
        h3.id = id;
        const category = getServiceCategory(h3.textContent);
        h3.setAttribute('data-category', category);

        let next = h3.nextElementSibling;
        while (next && next.tagName !== 'H3') {
            next.setAttribute('data-category', category);
            next = next.nextElementSibling;
        }

        const link = document.createElement('a');
        link.href = '#' + id;
        link.className = 'sub-nav-item';
        link.textContent = h3.textContent.split(' - ')[0];
        link.setAttribute('data-svc-id', id);
        link.setAttribute('data-category', category);
        subNav.appendChild(link);
    });
}

/**
 * Pagination System (V2 - Support Filtering & Sorting)
 */
const paginationStates = {};

function updateAllPaginations() {
    const tables = document.querySelectorAll('table[id]');
    tables.forEach(table => {
        const tableId = table.id;
        if (!paginationStates[tableId]) {
            paginationStates[tableId] = { currentPage: 1 };
        }
        showTablePage(tableId, paginationStates[tableId].currentPage);
    });
}

function showTablePage(tableId, page) {
    const table = document.getElementById(tableId);
    const paginationId = tableId.replace('-table', '-pagination');
    const paginationContainer = document.getElementById(paginationId);
    if (!table || !paginationContainer) return;

    const tbody = table.querySelector('tbody');
    // Ambil semua baris yang TIDAK sedang di-filter hide
    const visibleRows = Array.from(tbody.querySelectorAll('tr:not(.filtered-hidden)'));
    const rowsPerPage = 10;
    const totalPages = Math.ceil(visibleRows.length / rowsPerPage);

    if (totalPages <= 1) {
        // Sembunyikan pagination jika cuma 1 halaman
        paginationContainer.style.display = 'none';
        // Reset semua baris ke visible (selama tidak di-filter)
        Array.from(tbody.querySelectorAll('tr')).forEach(r => r.classList.remove('page-hidden'));
        return;
    }

    paginationContainer.style.display = 'flex';
    if (page > totalPages) page = totalPages;
    if (page < 1) page = 1;

    paginationStates[tableId].currentPage = page;

    const start = (page - 1) * rowsPerPage;
    const end = start + rowsPerPage;

    // Sembunyikan SEMUA baris dulu
    Array.from(tbody.querySelectorAll('tr')).forEach(r => r.classList.add('page-hidden'));

    // Tampilkan hanya baris pada halaman ini (dari list visibleRows)
    visibleRows.forEach((row, index) => {
        if (index >= start && index < end) {
            row.classList.remove('page-hidden');
        }
    });

    renderPaginationLinks(paginationContainer, tableId, page, totalPages);
}

function renderPaginationLinks(container, tableId, currentPage, totalPages) {
    container.innerHTML = '';

    const prevBtn = document.createElement('button');
    prevBtn.innerHTML = '←';
    prevBtn.disabled = currentPage === 1;
    prevBtn.onclick = () => showTablePage(tableId, currentPage - 1);
    container.appendChild(prevBtn);

    // Smart pagination showing first, last, and neighbors
    const maxVisible = 5;
    let start = Math.max(1, currentPage - 2);
    let end = Math.min(totalPages, start + maxVisible - 1);

    if (end - start < maxVisible - 1) {
        start = Math.max(1, end - maxVisible + 1);
    }

    if (start > 1) {
        const first = document.createElement('button');
        first.textContent = '1';
        first.onclick = () => showTablePage(tableId, 1);
        container.appendChild(first);
        if (start > 2) container.appendChild(createDots());
    }

    for (let i = start; i <= end; i++) {
        const btn = document.createElement('button');
        btn.textContent = i;
        btn.className = i === currentPage ? 'active' : '';
        btn.onclick = () => showTablePage(tableId, i);
        container.appendChild(btn);
    }

    if (end < totalPages) {
        if (end < totalPages - 1) container.appendChild(createDots());
        const last = document.createElement('button');
        last.textContent = totalPages;
        last.onclick = () => showTablePage(tableId, totalPages);
        container.appendChild(last);
    }

    const nextBtn = document.createElement('button');
    nextBtn.innerHTML = '→';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.onclick = () => showTablePage(tableId, currentPage + 1);
    container.appendChild(nextBtn);
}

function createDots() {
    const span = document.createElement('span');
    span.className = 'page-info';
    span.textContent = '...';
    return span;
}

/**
 * Filter & Search Integration
 */
function filterByCategory(category) {
    const inventory = document.getElementById('services-inventory');
    const elements = inventory.querySelectorAll('[data-category]');
    const sidebarLinks = document.querySelectorAll('.sub-nav-item');
    let visibleSectionCount = 0;

    elements.forEach(el => {
        const elCat = el.getAttribute('data-category');
        if (category === 'all' || elCat === category) {
            el.classList.remove('filtered-hidden');
            if (el.tagName === 'H3') visibleSectionCount++;
        } else {
            el.classList.add('filtered-hidden');
        }
    });

    // Update sidebar links
    sidebarLinks.forEach(link => {
        const linkCat = link.getAttribute('data-category');
        if (category === 'all' || linkCat === category) {
            link.classList.remove('filtered-hidden');
        } else {
            link.classList.add('filtered-hidden');
        }
    });

    // Update Pagination state for all tables
    updateAllPaginations();
    updateNoResultsMessage(visibleSectionCount);
}

let searchTimeout;
function searchResources(query) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        const q = query.toLowerCase().trim();
        const inventory = document.getElementById('services-inventory');
        const tables = inventory.querySelectorAll('table');
        let foundAny = false;

        if (!q) {
            // Reset filter hidden classes
            inventory.querySelectorAll('tr').forEach(r => r.classList.remove('filtered-hidden'));
            inventory.querySelectorAll('.table-wrapper, .service-detail-card, h3').forEach(el => el.classList.remove('filtered-hidden'));

            // Reset sidebar links
            document.querySelectorAll('.sub-nav-item').forEach(link => link.classList.remove('filtered-hidden'));

            updateAllPaginations();
            updateNoResultsMessage(-1);
            return;
        }

        tables.forEach(table => {
            const rows = table.querySelectorAll('tbody tr');
            let tableHasMatch = false;

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(q)) {
                    row.classList.remove('filtered-hidden');
                    tableHasMatch = true;
                    foundAny = true;
                } else {
                    row.classList.add('filtered-hidden');
                }
            });

            // Hide container if no match
            const container = table.closest('.table-wrapper, .service-detail-card');
            if (container) {
                let h3 = container.previousElementSibling;
                while (h3 && h3.tagName !== 'H3') h3 = h3.previousElementSibling;

                if (tableHasMatch) {
                    container.classList.remove('filtered-hidden');
                    if (h3) h3.classList.remove('filtered-hidden');
                } else {
                    container.classList.add('filtered-hidden');
                    if (h3) h3.classList.add('filtered-hidden');
                }

                // Sync sidebar link
                if (h3 && h3.id) {
                    const sidebarLink = document.querySelector(`.sub-nav-item[data-svc-id="${h3.id}"]`);
                    if (sidebarLink) {
                        if (tableHasMatch) sidebarLink.classList.remove('filtered-hidden');
                        else sidebarLink.classList.add('filtered-hidden');
                    }
                }
            }
        });

        updateAllPaginations();
        updateNoResultsMessage(foundAny ? 1 : 0);
    }, 300);
}

function resetFilters() {
    document.getElementById('category-filter').value = 'all';
    document.getElementById('search-filter').value = '';

    const inventory = document.getElementById('services-inventory');
    inventory.querySelectorAll('.filtered-hidden').forEach(el => el.classList.remove('filtered-hidden'));
    inventory.querySelectorAll('tr').forEach(r => r.classList.remove('filtered-hidden'));

    // Reset sidebar links
    document.querySelectorAll('.sub-nav-item').forEach(link => link.classList.remove('filtered-hidden'));

    updateAllPaginations();
    updateNoResultsMessage(-1);
}

function updateNoResultsMessage(count) {
    const noResults = document.getElementById('no-results');
    if (count === 0) noResults.classList.add('show');
    else noResults.classList.remove('show');
}

/**
 * Sort Tables
 */
function sortTable(table, columnIndex, direction) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort((a, b) => {
        const aCell = a.cells[columnIndex].textContent.trim();
        const bCell = b.cells[columnIndex].textContent.trim();

        const aVal = !isNaN(parseFloat(aCell.replace(/[$,]/g, ''))) ? parseFloat(aCell.replace(/[$,]/g, '')) : aCell.toLowerCase();
        const bVal = !isNaN(parseFloat(bCell.replace(/[$,]/g, ''))) ? parseFloat(bCell.replace(/[$,]/g, '')) : bCell.toLowerCase();

        if (direction === 'asc') return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
        else return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
    });

    rows.forEach(row => tbody.appendChild(row));
    // Trigger pagination update since order changed
    updateAllPaginations();
}

function makeSortable() {
    const tables = document.querySelectorAll('table');
    tables.forEach(table => {
        const headers = table.querySelectorAll('th');
        headers.forEach((header, index) => {
            header.classList.add('sortable');
            header.addEventListener('click', () => {
                const currentDir = header.classList.contains('asc') ? 'desc' : 'asc';
                headers.forEach(h => h.classList.remove('asc', 'desc'));
                header.classList.add(currentDir);
                sortTable(table, index, currentDir);
            });
        });
    });
}

/**
 * Main Initialization
 */
window.addEventListener('DOMContentLoaded', () => {
    buildDynamicMenu();
    makeSortable();

    document.getElementById('category-filter').addEventListener('change', (e) => filterByCategory(e.target.value));
    document.getElementById('search-filter').addEventListener('input', (e) => searchResources(e.target.value));

    // Initialize Paginations
    updateAllPaginations();

    // Smooth Scroll & Scroll Spy
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                window.scrollTo({ top: target.offsetTop - 20, behavior: 'smooth' });
            }
        });
    });

    window.addEventListener('scroll', () => {
        let current = '';
        const sections = document.querySelectorAll('.section, h3[id]');
        sections.forEach(s => {
            if (pageYOffset >= (s.offsetTop - 100)) current = s.id;
        });
        document.querySelectorAll('.nav-item, .sub-nav-item').forEach(a => {
            a.classList.remove('active');
            if (a.getAttribute('href') === '#' + current) a.classList.add('active');
        });
    });
});
