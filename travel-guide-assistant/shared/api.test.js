import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function loadApi(chunks) {
  var chunkIndex = 0;
  var context = {
    Error: Error,
    JSON: JSON,
    Promise: Promise,
    TextDecoder: TextDecoder,
    console: console,
    window: { TravelMate: { utils: { API_BASE: 'http://test' } } },
    fetch: function () {
      return Promise.resolve({
        ok: true,
        body: {
          getReader: function () {
            return {
              read: function () {
                if (chunkIndex >= chunks.length) {
                  return Promise.resolve({ done: true });
                }
                return Promise.resolve({
                  done: false,
                  value: Buffer.from(chunks[chunkIndex++], 'utf8')
                });
              }
            };
          }
        }
      });
    }
  };
  var source = fs.readFileSync(path.join(__dirname, 'api.js'), 'utf8');
  vm.runInNewContext(source, context, { filename: 'shared/api.js' });
  return context.window.TravelMate.api;
}

test('chatStream dispatches itinerary when event and data arrive separately', async function () {
  var itinerary = {
    destination: '京都',
    days: 7,
    total_budget: 8500,
    day_plans: [],
    tips: []
  };
  var api = loadApi([
    'event: itinerary\r\n',
    'data: ' + JSON.stringify(itinerary) + '\r\n\r\n',
    'event: done\r\ndata: {"id":"chat-1","usage":{}}\r\n\r\n'
  ]);
  var receivedItinerary = null;

  await new Promise(function (resolve) {
    api.chatStream('五一去日本玩7天', {
      onItinerary: function (payload) { receivedItinerary = payload; },
      onDone: resolve
    });
  });

  assert.deepEqual(receivedItinerary, itinerary);
});
