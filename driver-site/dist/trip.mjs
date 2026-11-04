import {escapeHtml, parseToken} from './domain.mjs';

const key = 'transportorder.driver.trip';
const lifetime = 7 * 24 * 60 * 60 * 1000;

export function trip() {
  try {
    const records = JSON.parse(localStorage.getItem(key) || '[]');
    return records.filter(record => /^[a-f0-9]{64}$/.test(record.token) && record.expires > Date.now());
  } catch {
    return [];
  }
}

export function rememberShipment(token, shipment) {
  const records = trip();
  const previous = records.find(record => record.token === token);
  const expires = previous?.expires || Date.now() + lifetime;
  const next = [{token, expires, building: shipment.building, id: shipment.id},
    ...records.filter(record => record.token !== token)].slice(0, 20);
  try { localStorage.setItem(key, JSON.stringify(next)); } catch {}
}

export function forgetTrip() {
  try { localStorage.removeItem(key); } catch {}
}

export function tripLinks(currentToken) {
  const records = trip().filter(record => record.token !== currentToken);
  if (!records.length) return '';
  return `<section class="card portal-result"><h2>${currentToken ? 'Other stops on this truck' : 'Return to your shipment'}</h2>
    <div class="trip-links">${records.map(record => `<a class="btn secondary" href="./#${record.token}">${escapeHtml(record.building)} · ${escapeHtml(record.id)}</a>`).join('')}</div>
    ${currentToken ? '' : '<button type="button" class="text-link" data-portal="forget-trip">Clear saved shipments</button>'}</section>`;
}

export function manifestToken(value) {
  try {
    const url = new URL(value.trim());
    if (url.origin === location.origin && url.pathname === location.pathname) return parseToken(url.hash);
  } catch {}
  return null;
}
