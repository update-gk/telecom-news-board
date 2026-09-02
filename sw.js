/*
 * 通信業界レーダー - Service Worker
 * - アプリ本体(シェル)はキャッシュ優先で即表示
 * - data/news.json はネットワーク優先(取れなければ最後に取得できた内容を表示)
 * デプロイのたびに CACHE のバージョンを上げると、古いキャッシュを破棄して更新される。
 */
const CACHE = "telecom-radar-v4";
const SHELL = [
  "./",
  "./telecom-news-board.html",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
  "./icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // ニュースデータ: ネットワーク優先、失敗時キャッシュ
  if (url.pathname.endsWith("/data/news.json")) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // それ以外(アプリシェル等): キャッシュ優先、無ければ取得してキャッシュ
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((res) => {
          if (res.ok && url.origin === self.location.origin) {
            const copy = res.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return res;
        })
    )
  );
});
