window.LoqateClient = (() => {
  const findEndpoint = 'https://api.addressy.com/Capture/Interactive/Find/v1.20/json6.ws';
  const verifyEndpoint = 'https://api.addressy.com/Cleansing/International/Batch/v1.20/json6.ws';

  async function request(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();

    if (!response.ok) {
      throw new Error('LOQATE request failed with HTTP ' + response.status);
    }

    return data;
  }

  function getItems(data) {
    if (data && Array.isArray(data.Items)) return data.Items;
    if (Array.isArray(data)) return data;
    return [];
  }

  function throwIfApiError(items) {
    const error = items.find(item => item && item.Error);
    if (error) {
      throw new Error('LOQATE Error: ' + (error.Description || error.Error));
    }
  }

  async function search(apiKey, country, query) {
    const url = new URL(findEndpoint);
    url.searchParams.set('Key', apiKey);
    url.searchParams.set('Text', query);
    url.searchParams.set('Countries', country);
    url.searchParams.set('Limit', '100');

    let items = getItems(await request(url));
    if (items.length === 0) {
      throw new Error('No results returned from LOQATE. Check API key and parameters.');
    }

    throwIfApiError(items);

    let remainingDepth = 5;
    while (remainingDepth > 0 && items.length > 0 && items[0].Type !== 'Address') {
      url.searchParams.set('Container', items[0].Id);
      const containerItems = getItems(await request(url));
      throwIfApiError(containerItems);
      if (containerItems.length === 0) break;
      items = containerItems;
      remainingDepth--;
    }

    return items
      .filter(item => item.Type === 'Address')
      .map(item => ({ id: item.Id, text: item.Text, description: item.Description }));
  }

  async function retrieve(apiKey, result, country) {
    const payload = {
      Key: apiKey,
      GeoCode: true,
      Addresses: [{
        Id: result.id,
        Address: result.text,
        Address1: result.text,
        Locality: result.description,
        Country: country
      }],
      Options: {
        Process: 'Verify',
        Enhance: false,
        ServerOptions: { OutputAddressFormat: 'YES' }
      }
    };
    const data = await request(verifyEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const items = getItems(data);
    throwIfApiError(items);
    const item = items[0];
    if (!item) {
      throw new Error('No address details returned from LOQATE.');
    }
    return item.Matches && item.Matches[0] ? item.Matches[0] : item;
  }

  return { search, retrieve };
})();
