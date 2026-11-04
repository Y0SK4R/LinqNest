/**
 * LinkNest Frontend Validation Module
 * Enforces client-side validation rules matching backend security constraints.
 */

export const RESERVED_ROUTES = new Set([
  'api',
  'docs',
  'redoc',
  'openapi.json',
  'static',
  'health',
  'favicon.ico',
  'robots.txt'
]);

export const BLOCKED_HOSTNAMES = new Set([
  'localhost',
  '127.0.0.1',
  '::1',
  '0.0.0.0',
  'metadata.google.internal',
  'instance-data'
]);

export const DISALLOWED_TLD_SUFFIXES = [
  '.local',
  '.internal',
  '.lan',
  '.home',
  '.corp'
];

/**
 * Checks if an IPv4 string belongs to private or link-local ranges.
 */
function isPrivateIPv4(ipStr) {
  const parts = ipStr.split('.').map(Number);
  if (parts.length !== 4 || parts.some(p => isNaN(p) || p < 0 || p > 255)) {
    return false;
  }
  // 127.0.0.0/8 (Loopback)
  if (parts[0] === 127) return true;
  // 10.0.0.0/8 (Private)
  if (parts[0] === 10) return true;
  // 172.16.0.0/12 (Private)
  if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true;
  // 192.168.0.0/16 (Private)
  if (parts[0] === 192 && parts[1] === 168) return true;
  // 169.254.0.0/16 (Link-local / Cloud metadata)
  if (parts[0] === 169 && parts[1] === 254) return true;
  // 0.0.0.0/8
  if (parts[0] === 0) return true;

  return false;
}

/**
 * Validates a destination URL against security rules.
 * Returns { valid: boolean, error?: string, sanitizedUrl?: string }
 */
export function validateUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') {
    return { valid: false, error: 'URL cannot be empty.' };
  }

  const url = rawUrl.trim();
  if (url.length < 4) {
    return { valid: false, error: 'URL is too short.' };
  }
  if (url.length > 2048) {
    return { valid: false, error: 'URL exceeds maximum length of 2048 characters.' };
  }

  let parsed;
  try {
    parsed = new URL(url);
  } catch (err) {
    return { valid: false, error: 'Invalid URL structure. Ensure it begins with http:// or https://' };
  }

  const protocol = parsed.protocol.toLowerCase();
  if (protocol !== 'http:' && protocol !== 'https:') {
    return { valid: false, error: "Only 'http://' and 'https://' destinations are permitted." };
  }

  if (parsed.username || parsed.password) {
    return { valid: false, error: 'URLs containing embedded credentials are not allowed.' };
  }

  const hostname = parsed.hostname.toLowerCase();
  if (!hostname) {
    return { valid: false, error: 'URL must contain a valid hostname.' };
  }

  if (BLOCKED_HOSTNAMES.has(hostname)) {
    return { valid: false, error: 'Access to localhost and internal hostnames is prohibited.' };
  }

  for (const suffix of DISALLOWED_TLD_SUFFIXES) {
    if (hostname.endsWith(suffix)) {
      return { valid: false, error: `Local network domains (${suffix}) are prohibited.` };
    }
  }

  // Check IPv4 literal
  const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/;
  if (ipv4Regex.test(hostname)) {
    if (isPrivateIPv4(hostname)) {
      return { valid: false, error: `Destination IP address '${hostname}' is a restricted private/local address.` };
    }
  }

  return { valid: true, sanitizedUrl: parsed.href };
}

/**
 * Validates custom alias / short code.
 * Returns { valid: boolean, error?: string }
 */
export function validateCustomCode(rawCode) {
  if (!rawCode) {
    return { valid: true }; // optional
  }

  const code = rawCode.trim();
  if (code.length < 3 || code.length > 16) {
    return { valid: false, error: 'Custom code must be between 3 and 16 characters.' };
  }

  if (!/^[a-zA-Z0-9_-]+$/.test(code)) {
    return { valid: false, error: 'Custom code can only contain letters, numbers, hyphens, and underscores.' };
  }

  if (RESERVED_ROUTES.has(code.toLowerCase())) {
    return { valid: false, error: `'${code}' is a reserved system route.` };
  }

  return { valid: true, sanitizedCode: code };
}
