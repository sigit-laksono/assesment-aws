"""
Security Rules Engine
=====================
Evaluator sederhana yang membaca data inventaris dari `assessment_data['services']`
dan menghasilkan security findings ke `assessment_data['security_findings']`.

Setiap finding mengikuti skema:
{
    'id': str,             # ID unik (mis. 'EBS-001')
    'rule': str,           # Slug rule
    'severity': str,       # 'critical' | 'high' | 'medium' | 'low'
    'service': str,        # Nama service (EBS, CloudTrail, ...)
    'resource_id': str,    # ID resource yang melanggar
    'title': str,          # Judul finding (Bahasa Indonesia)
    'description': str,    # Deskripsi singkat masalah
    'recommendation': str  # Tindakan rekomendasi
}

Best practice referensi:
- AWS Well-Architected Framework — Security Pillar
- CIS AWS Foundations Benchmark
"""


def _next_id(prefix, counter):
    counter[prefix] = counter.get(prefix, 0) + 1
    return f"{prefix}-{counter[prefix]:03d}"


def _rule_ebs_unencrypted(assessment_data, findings, counter):
    """CIS 2.2.1 — EBS Volumes harus dienkripsi at-rest."""
    ebs = assessment_data.get('services', {}).get('ebs')
    if not ebs:
        return

    for vol in ebs.get('volumes', []):
        if not vol.get('encrypted', False):
            findings.append({
                'id': _next_id('EBS', counter),
                'rule': 'ebs_unencrypted',
                'severity': 'high',
                'service': 'EBS',
                'resource_id': vol.get('id', 'N/A'),
                'title': 'EBS Volume tidak terenkripsi',
                'description': (
                    f"Volume {vol.get('id')} ({vol.get('size')} GB, "
                    f"type {vol.get('type')}) tidak menggunakan enkripsi at-rest."
                ),
                'recommendation': (
                    "Aktifkan EBS Encryption by Default pada region ini, "
                    "lalu migrasikan volume existing dengan membuat snapshot, "
                    "copy snapshot dengan opsi encrypted, dan restore ke volume baru."
                )
            })


def _rule_cloudtrail_not_multi_region(assessment_data, findings, counter):
    """CIS 3.1 — Setidaknya satu CloudTrail trail harus multi-region."""
    ct = assessment_data.get('services', {}).get('cloudtrail')
    if not ct:
        return

    trails = ct.get('trails', [])

    # Kalau tidak ada trail sama sekali, ini critical
    if not trails:
        findings.append({
            'id': _next_id('CT', counter),
            'rule': 'cloudtrail_missing',
            'severity': 'critical',
            'service': 'CloudTrail',
            'resource_id': 'N/A',
            'title': 'CloudTrail tidak dikonfigurasi',
            'description': "Tidak ditemukan CloudTrail trail aktif pada account ini.",
            'recommendation': (
                "Buat minimal 1 CloudTrail trail multi-region dengan log file "
                "validation enabled dan kirim log ke S3 bucket yang dilindungi."
            )
        })
        return

    has_multi_region_active = any(
        t.get('is_multi_region') and t.get('is_logging') for t in trails
    )

    if not has_multi_region_active:
        # Tandai trail-trail yang single-region sebagai bukti
        for trail in trails:
            if not trail.get('is_multi_region', False):
                findings.append({
                    'id': _next_id('CT', counter),
                    'rule': 'cloudtrail_not_multi_region',
                    'severity': 'high',
                    'service': 'CloudTrail',
                    'resource_id': trail.get('name', 'N/A'),
                    'title': 'CloudTrail trail bukan multi-region',
                    'description': (
                        f"Trail '{trail.get('name')}' hanya merekam event "
                        "dari satu region. Aktivitas API di region lain tidak teraudit."
                    ),
                    'recommendation': (
                        "Ubah konfigurasi trail menjadi multi-region "
                        "(IsMultiRegionTrail=true) atau buat trail baru yang "
                        "multi-region untuk mencakup seluruh region."
                    )
                })


# Daftar rule yang akan dijalankan. Tambahkan rule baru di sini.
_RULES = [
    _rule_ebs_unencrypted,
    _rule_cloudtrail_not_multi_region,
]


def evaluate(assessment_data):
    """Jalankan semua rule dan tulis hasilnya ke assessment_data['security_findings']."""
    print("\n🔒 Mengevaluasi security rules...")
    findings = []
    counter = {}

    for rule in _RULES:
        try:
            rule(assessment_data, findings, counter)
        except Exception as e:
            print(f"  ⚠ Rule {rule.__name__} gagal: {e}")

    assessment_data['security_findings'] = findings

    # Ringkasan ke stdout
    severity_count = {}
    for f in findings:
        sev = f['severity']
        severity_count[sev] = severity_count.get(sev, 0) + 1

    if findings:
        summary = ", ".join(f"{v} {k}" for k, v in severity_count.items())
        print(f"✓ {len(findings)} security findings ditemukan ({summary})")
    else:
        print("✓ Tidak ditemukan security findings dari rule yang dijalankan")

    return findings
