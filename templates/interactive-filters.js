/**
 * Interactive Filters for AWS Assessment Report
 * Implementasi yang benar berdasarkan fix-bug-filtering.html
 */

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
        
        // Cari elemen berikutnya sampai H3 selanjutnya untuk dikelompokkan
        let next = h3.nextElementSibling;
        while(next && next.tagName !== 'H3') {
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
 * Filter berdasarkan Kategori
 */
function filterByCategory(category) {
    const inventory = document.getElementById('services-inventory');
    const elements = inventory.querySelectorAll('[data-category]');
    const sidebarLinks = document.querySelectorAll('.sub-nav-item');
    let visibleCount = 0;

    elements.forEach(el => {
        const elCat = el.getAttribute('data-category');
        if (category === 'all' || elCat === category) {
            el.classList.remove('filtered-hidden');
            if (el.tagName === 'H3') visibleCount++;
        } else {
            el.classList.add('filtered-hidden');
        }
    });

    sidebarLinks.forEach(link => {
        const linkCat = link.getAttribute('data-category');
        if (category === 'all' || linkCat === category) {
            link.classList.remove('filtered-hidden');
        } else {
            link.classList.add('filtered-hidden');
        }
    });

    updateNoResultsMessage(visibleCount);
}

/**
 * Pencarian Resources
 */
let searchTimeout;
function searchResources(query) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        const q = query.toLowerCase().trim();
        const inventory = document.getElementById('services-inventory');
        const tables = inventory.querySelectorAll('table');
        let foundAny = false;

        if (!q) {
            // Reset search - show all
            const allRows = inventory.querySelectorAll('tbody tr');
            allRows.forEach(row => row.classList.remove('filtered-hidden'));
            
            const allContainers = inventory.querySelectorAll('.table-wrapper, .service-detail-card, h3');
            allContainers.forEach(el => el.classList.remove('filtered-hidden'));
            
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

            // Sembunyikan container tabel jika tidak ada baris yang cocok
            const container = table.closest('.table-wrapper, .service-detail-card');
            if (container) {
                // Cari H3 sebelumnya
                let prevElement = container.previousElementSibling;
                while (prevElement && prevElement.tagName !== 'H3') {
                    prevElement = prevElement.previousElementSibling;
                }

                if (tableHasMatch) {
                    container.classList.remove('filtered-hidden');
                    if (prevElement && prevElement.tagName === 'H3') {
                        prevElement.classList.remove('filtered-hidden');
                    }
                } else {
                    container.classList.add('filtered-hidden');
                    if (prevElement && prevElement.tagName === 'H3') {
                        prevElement.classList.add('filtered-hidden');
                    }
                }
            }
        });

        updateNoResultsMessage(foundAny ? 1 : 0);
    }, 300);
}

/**
 * Update No Results Message
 */
function updateNoResultsMessage(count) {
    const noResults = document.getElementById('no-results');
    if (count === 0) {
        noResults.classList.add('show');
    } else {
        noResults.classList.remove('show');
    }
}

/**
 * Reset Filters
 */
function resetFilters() {
    document.getElementById('category-filter').value = 'all';
    document.getElementById('search-filter').value = '';
    
    const inventory = document.getElementById('services-inventory');
    const hiddenElements = inventory.querySelectorAll('.filtered-hidden');
    hiddenElements.forEach(el => el.classList.remove('filtered-hidden'));
    
    const sidebarLinks = document.querySelectorAll('.sub-nav-item');
    sidebarLinks.forEach(link => link.classList.remove('filtered-hidden'));
    
    updateNoResultsMessage(-1);
}

/**
 * Sort Table
 */
function sortTable(table, columnIndex, direction) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    
    rows.sort((a, b) => {
        const aCell = a.cells[columnIndex].textContent.trim();
        const bCell = b.cells[columnIndex].textContent.trim();
        
        const aVal = !isNaN(parseFloat(aCell)) ? parseFloat(aCell) : aCell.toLowerCase();
        const bVal = !isNaN(parseFloat(bCell)) ? parseFloat(bCell) : bCell.toLowerCase();
        
        if (direction === 'asc') {
            return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
        } else {
            return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
        }
    });
    
    rows.forEach(row => tbody.appendChild(row));
}

/**
 * Make Tables Sortable
 */
function makeSortable() {
    const tables = document.querySelectorAll('table');
    
    tables.forEach(table => {
        const headers = table.querySelectorAll('th');
        
        headers.forEach((header, index) => {
            header.classList.add('sortable');
            header.style.cursor = 'pointer';
            
            let currentDirection = null;
            
            header.addEventListener('click', () => {
                headers.forEach(h => {
                    if (h !== header) {
                        h.classList.remove('asc', 'desc');
                    }
                });
                
                if (currentDirection === 'asc') {
                    currentDirection = 'desc';
                    header.classList.remove('asc');
                    header.classList.add('desc');
                } else {
                    currentDirection = 'asc';
                    header.classList.remove('desc');
                    header.classList.add('asc');
                }
                
                sortTable(table, index, currentDirection);
            });
        });
    });
}

/**
 * Pagination
 */
function initializePagination() {
    const tables = document.querySelectorAll('table[id]');
    
    tables.forEach(table => {
        const tableId = table.id;
        const paginationId = tableId.replace('-table', '-pagination');
        const paginationContainer = document.getElementById(paginationId);
        
        if (!paginationContainer) return;
        
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const rowsPerPage = 10;
        const totalPages = Math.ceil(rows.length / rowsPerPage);
        
        if (totalPages <= 1) {
            paginationContainer.style.display = 'none';
            return;
        }
        
        let currentPage = 1;
        
        function showPage(page) {
            currentPage = page;
            const start = (page - 1) * rowsPerPage;
            const end = start + rowsPerPage;
            
            rows.forEach((row, index) => {
                if (index >= start && index < end) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
            
            renderPagination();
        }
        
        function renderPagination() {
            paginationContainer.innerHTML = '';
            
            // Previous button
            const prevBtn = document.createElement('button');
            prevBtn.innerHTML = '←';
            prevBtn.disabled = currentPage === 1;
            prevBtn.onclick = () => showPage(currentPage - 1);
            paginationContainer.appendChild(prevBtn);
            
            // Page numbers with smart display
            const maxVisiblePages = 5;
            let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
            let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
            
            if (endPage - startPage < maxVisiblePages - 1) {
                startPage = Math.max(1, endPage - maxVisiblePages + 1);
            }
            
            // First page + dots if needed
            if (startPage > 1) {
                const firstBtn = document.createElement('button');
                firstBtn.textContent = '1';
                firstBtn.onclick = () => showPage(1);
                paginationContainer.appendChild(firstBtn);
                
                if (startPage > 2) {
                    const dots = document.createElement('span');
                    dots.className = 'page-info';
                    dots.textContent = '...';
                    paginationContainer.appendChild(dots);
                }
            }
            
            // Visible page numbers
            for (let i = startPage; i <= endPage; i++) {
                const pageBtn = document.createElement('button');
                pageBtn.textContent = i;
                pageBtn.className = i === currentPage ? 'active' : '';
                pageBtn.onclick = () => showPage(i);
                paginationContainer.appendChild(pageBtn);
            }
            
            // Last page + dots if needed
            if (endPage < totalPages) {
                if (endPage < totalPages - 1) {
                    const dots = document.createElement('span');
                    dots.className = 'page-info';
                    dots.textContent = '...';
                    paginationContainer.appendChild(dots);
                }
                
                const lastBtn = document.createElement('button');
                lastBtn.textContent = totalPages;
                lastBtn.onclick = () => showPage(totalPages);
                paginationContainer.appendChild(lastBtn);
            }
            
            // Next button
            const nextBtn = document.createElement('button');
            nextBtn.innerHTML = '→';
            nextBtn.disabled = currentPage === totalPages;
            nextBtn.onclick = () => showPage(currentPage + 1);
            paginationContainer.appendChild(nextBtn);
        }
        
        // Initialize first page
        showPage(1);
    });
}

/**
 * Initialize
 */
window.addEventListener('DOMContentLoaded', () => {
    buildDynamicMenu();
    makeSortable();

    document.getElementById('category-filter').addEventListener('change', (e) => {
        filterByCategory(e.target.value);
        document.getElementById('search-filter').value = '';
    });

    document.getElementById('search-filter').addEventListener('input', (e) => {
        searchResources(e.target.value);
    });

    // Smooth Scroll
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                window.scrollTo({ 
                    top: target.offsetTop - 20, 
                    behavior: 'smooth' 
                });
            }
        });
    });

    // Scroll Spy
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

    // Initialize pagination
    initializePagination();
});
