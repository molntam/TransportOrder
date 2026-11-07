import csv
import hashlib
import io
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from .sap import InputError, identifier, quantity

DEFAULT_REPORT_URL = ('https://spotfire.asml.com/spotfire/wp/analysis?'
                      'file=/ASML/Production/5L/Reports/Self.Service/LO%20Outbound/'
                      'FIFO%20Monitor%20DHL%20Shipping')
PAGE_NAME = 'Data Table Monitor'
REQUIRED = ('handlingunit', 'originalerpdocument', 'shiptopartydescription', 'quantity')
ALIASES = {
    'ASML BLD 9 DESK9': 'DESK9C',
    'DHL TOOLS': 'DHL.TOOLSC',
    'WH 21 MPS': 'WH21-MPSC',
    'WEERT 1A': 'WH-WEERT1A',
    'ASML WEERT 1A': 'WH-WEERT1A',
}


def normalise(value):
    return ' '.join(re.findall(r'[A-Z0-9]+', str(value).upper()))


def report_url(value):
    parts = urlsplit(str(value).strip())
    query = parse_qs(parts.query)
    if (parts.scheme != 'https' or parts.hostname != 'spotfire.asml.com'
            or parts.port not in (None, 443) or parts.username or parts.password
            or parts.path != '/spotfire/wp/analysis' or not query.get('file')):
        raise InputError('Use the HTTPS Spotfire analysis link from spotfire.asml.com, including file=.')
    if any(mark in query['file'][0] for mark in ('…', '...')):
        raise InputError('Paste the complete Spotfire report link.')
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode({'file': query['file'][0]}), ''))


def decode_export(content):
    if isinstance(content, str):
        return content.lstrip('\ufeff')
    if len(content) > 20_000_000:
        raise InputError('Spotfire exports are limited to 20 MB.')
    try:
        return content.decode('utf-16' if content.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    except UnicodeError as exc:
        raise InputError('Export Spotfire as UTF-8 or UTF-16 CSV/TSV.') from exc


def parse_export(content):
    text = decode_export(content)
    header = text.splitlines()[0] if text.strip() else ''
    delimiter = '\t' if '\t' in header else ';' if ';' in header else ','
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    labels = next(reader, [])
    keys = [re.sub(r'[^a-z0-9]', '', label.lower()) for label in labels]
    missing = [key for key in REQUIRED if key not in keys]
    if missing or len(set(keys)) != len(keys):
        raise InputError('Spotfire export needs unique Handling unit, Original_ERP_Document, '
                         'Ship_To_Party_Description and Quantity columns.')
    groups, quantities, warnings = {}, [], set()
    from ..domain import LOCATIONS
    routes = {normalise(code): code for code in LOCATIONS['automatic']}
    routes.update(ALIASES)
    for number, values in enumerate(reader, 2):
        if not any(value.strip() for value in values):
            continue
        if number > 50_001:
            raise InputError('Spotfire supports at most 50,000 item rows.')
        if len(values) != len(keys):
            raise InputError(f'Spotfire row {number} has a different number of columns.')
        row = dict(zip(keys, values))
        hu = identifier(row['handlingunit'])
        dn = identifier(row['originalerpdocument'])
        document = identifier(row.get('documentnumber', '')) or dn
        description = row['shiptopartydescription'].strip()
        if not hu or not dn or not description:
            raise InputError(f'Spotfire row {number} needs HU, original ERP document and ship-to description.')
        destination = routes.get(normalise(description), description)
        if normalise(description) not in routes:
            warnings.add(f'Unmapped ship-to: {description}. Review its destination when processing its HUs.')
        condition = row.get('erpshippingcondition', '').strip().upper()
        if condition not in ('S4', 'I2') and re.search(r'\bemergency\b', row.get('shippingconditions', ''), re.I):
            condition = 'S4'
        ship = {'hu': hu, 'dn': dn, 'document': document, 'shipTo': destination,
                'shipToDescription': description, 'condition': condition, 'externalId': '',
                'bin': row.get('storagebin', '').strip(), 'fifoAt': row.get('dhlkpidatetime', '').strip(),
                'changedOn': '', 'changedAt': '', 'provider': 'spotfire'}
        previous = groups.get(hu)
        if previous:
            if any(previous[field] != ship[field] for field in ('dn', 'document', 'shipTo')):
                raise InputError(f'Spotfire has conflicting documents or destinations for HU {hu}.')
            if condition in ('S4', 'I2'):
                previous['condition'] = condition
            if ship['bin'] and ship['bin'] not in previous['bin'].split(' / '):
                previous['bin'] = ' / '.join(filter(None, (previous['bin'], ship['bin'])))
        else:
            groups[hu] = ship
        try:
            amount = quantity(row['quantity'])
        except InputError as exc:
            raise InputError(f'Spotfire row {number}: {exc}') from exc
        quantities.append({'hu': hu, 'document': document, 'qty': amount, 'provider': 'spotfire'})
    ships = list(groups.values())
    sources = {}
    for kind, rows in (('shipto', ships), ('quantities', quantities)):
        sources[kind] = {'rows': rows, 'count': len(rows), 'uniqueHus': len(groups),
                         'warnings': sorted(warnings), 'filename': 'Spotfire — Data Table Monitor',
                         'provider': 'spotfire'}
    fingerprint = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    return {'sources': sources, 'fingerprint': fingerprint, 'rowCount': len(quantities),
            'uniqueHus': len(groups), 'warnings': sorted(warnings)}


class SpotfireProvider:
    id = 'spotfire'
    label = 'Spotfire — Data Table Monitor'
    available = True
    description = 'CSV collection from the signed-in report tab every 60 seconds.'
    parse = staticmethod(parse_export)
