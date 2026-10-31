/** Board-game configuration; common browsing, loading and collection code is shared. */
window.TOONPICK_PAGE = {
  type: 'boardgame',
  catalogEndpoint: '/api/generate?resource=boardgame_catalog',
  fallbackEndpoint: '/data/boardgames_catalog.json',
  storageKey: 'toonpick_saved_boardgames',
  genres: ['전략', '협력', '파티', '가족', '추리', '카드', '퍼즐', '2인', '심리전'],
  moods: ['전체', '가볍게', '머리쓰는', '함께하는', '웃음가득', '긴장감', '차분한'],
  statuses: ['전체'],
  platforms: { boardgames: { key: 'boardgames', name: '공식 게임 정보', workHosts: ['www.spacecowboys-games.com', 'www.nsv.de', 'www.nextmove-games.com', 'www.czechgames.com', 'www.blueorangegames.com', 'www.hans-im-glueck.de', 'www.asmodee.ca', 'www.lookout-spiele.de', 'www.rprod.com', 'store.asmodee.com', 'www.cocktailgames.com', 'blog.amigo-spiele.de', 'www.gamewright.com', 'www.catan.com', 'www.zmangames.com', 'www.asmodee.co.uk', 'www.alderac.com', 'pandasaurusgames.com', 'www.amigo-spiele.de', 'oinkgames.com', 'pegasusna.com', 'www.koreaboardgames.com'], workPattern: '^/.*$', imageHosts: ['cdnfile.koreaboardgames.com'] } }
};
