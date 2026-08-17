import json, requests, traceback
try:
    env = {}
    for line in open('.env', encoding='utf-8').read().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    tok = json.loads(open('memory_data/spotify_token.json').read())
    r = requests.post('https://accounts.spotify.com/api/token',
                      data={'grant_type': 'refresh_token', 'refresh_token': tok['refresh_token']},
                      auth=(env['SPOTIFY_CLIENT_ID'], env['SPOTIFY_CLIENT_SECRET']), timeout=15)
    h = {'Authorization': 'Bearer ' + r.json()['access_token']}

    # search for a track
    s = requests.get('https://api.spotify.com/v1/search',
                     params={'q': 'ElGrandeToto', 'type': 'track', 'limit': 1},
                     headers=h, timeout=15)
    print('search:', s.status_code)
    uri = s.json()['tracks']['items'][0]['uri']
    print('track uri:', uri)

    # get devices
    dev = requests.get('https://api.spotify.com/v1/me/player/devices', headers=h, timeout=15)
    print('devices:', dev.status_code, dev.text)
    devices = dev.json().get('devices', [])
    if devices:
        dev_id = devices[0]['id']
        print('device id:', dev_id)
        # try playing WITH device_id
        p = requests.put('https://api.spotify.com/v1/me/player/play',
                         json={'uris': [uri]},
                         params={'device_id': dev_id},
                         headers=h, timeout=10)
        print('play with device_id:', p.status_code, p.text)
    else:
        print('NO DEVICES AVAILABLE')
except Exception:
    traceback.print_exc()
