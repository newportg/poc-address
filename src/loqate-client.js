window.LoqateClient = (() => {
  function apiUrl(path) {
    const baseUrl = (window.ADDRESS_API_BASE_URL || '').replace(/\/+$/, '');
    return `${baseUrl}${path}`;
  }

  async function request(url, options) {
    const response = await fetch(url, options);
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(`Address API returned invalid JSON (HTTP ${response.status}).`);
    }

    if (!response.ok) {
      const detail = data && typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`;
      throw new Error(detail);
    }
    return data;
  }

  function headers(apiKey, includeJson = false) {
    return {
      Accept: 'application/json',
      'X-Loqate-Api-Key': apiKey,
      ...(includeJson ? { 'Content-Type': 'application/json' } : {})
    };
  }

  async function search(apiKey, country, query) {
    const url = new URL(apiUrl('/api/addresses/search'), window.location.href);
    url.searchParams.set('q', query);
    url.searchParams.set('country', country);
    const data = await request(url, { headers: headers(apiKey) });
    return Array.isArray(data.items) ? data.items : [];
  }

  async function retrieve(apiKey, result, country) {
    const data = await request(apiUrl('/api/addresses/retrieve'), {
      method: 'POST',
      headers: headers(apiKey, true),
      body: JSON.stringify({
        id: result.id,
        text: result.text,
        description: result.description || '',
        country
      })
    });
    return data;
  }

  return { search, retrieve };
})();
