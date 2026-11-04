/**
 * LinkNest API Client
 * Interacts with FastAPI backend v1 endpoints with standardized error handling.
 */

const API_BASE = '/api/v1';

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message);
    this.name = 'ApiError';
    this.code = code || 'UNKNOWN_ERROR';
    this.status = status || 500;
  }
}

/**
 * Parses response error body into a clean message and error code.
 */
async function parseErrorResponse(response) {
  let message = `Request failed with status ${response.status}`;
  let code = 'HTTP_ERROR';

  try {
    const data = await response.json();
    if (data && data.detail) {
      if (typeof data.detail === 'object' && !Array.isArray(data.detail)) {
        message = data.detail.message || message;
        code = data.detail.code || code;
      } else if (typeof data.detail === 'string') {
        message = data.detail;
      } else if (Array.isArray(data.detail) && data.detail.length > 0) {
        // FastAPI / Pydantic validation error array
        message = data.detail.map(d => d.msg || `${d.loc?.join('.')}: invalid`).join('; ');
        code = 'VALIDATION_ERROR';
      }
    }
  } catch (_) {
    // Non-JSON response
  }

  return new ApiError(message, code, response.status);
}

export const api = {
  /**
   * Fetch paginated list of created links.
   */
  async getLinks(skip = 0, limit = 50) {
    try {
      const res = await fetch(`${API_BASE}/links?skip=${skip}&limit=${limit}`);
      if (!res.ok) {
        throw await parseErrorResponse(res);
      }
      return await res.json();
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Unable to reach server. Please check your network connection.', 'NETWORK_ERROR', 0);
    }
  },

  /**
   * Create a new shortened link.
   * payload: { original_url, custom_code?, title? }
   */
  async createLink(payload) {
    try {
      const res = await fetch(`${API_BASE}/links`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        throw await parseErrorResponse(res);
      }
      return await res.json();
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Unable to submit link. Please check your connection.', 'NETWORK_ERROR', 0);
    }
  },

  /**
   * Fetch link stats by short code.
   */
  async getLinkStats(shortCode) {
    try {
      const res = await fetch(`${API_BASE}/links/${encodeURIComponent(shortCode)}/stats`);
      if (!res.ok) {
        throw await parseErrorResponse(res);
      }
      return await res.json();
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError('Failed to load link statistics.', 'NETWORK_ERROR', 0);
    }
  }
};
