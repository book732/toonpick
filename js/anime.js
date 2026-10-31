/** Anime-only configuration. The shared controller and service keep their public names. */
window.TOONPICK_PAGE = {
  type: 'anime',
  catalogEndpoint: '/api/generate?resource=anime_catalog',
  genres: ['액션', '모험', '코미디', '드라마', '판타지', '공포', '음악', '미스터리', '로맨스', 'SF', '일상', '스포츠', '스릴러', '초자연'],
  formats: { TV: 'TV 시리즈', MOVIE: '극장판', ONA: '웹 애니메이션', OVA: 'OVA', SPECIAL: '스페셜', TV_SHORT: '단편 TV' },
  statuses: ['전체', '연재', '완결', '휴재', '방영예정', '중단'],
  platforms: {
    laftel: { key: 'laftel', name: '라프텔', home: 'https://laftel.net/', workHosts: ['laftel.net'], workPattern: '^/item/[0-9]+(?:/.*)?$', imageHosts: ['thumbnail.laftel.net'] },
    netflix: { key: 'netflix', name: '넷플릭스', home: 'https://www.netflix.com/kr/browse/genre/7424', workHosts: ['www.netflix.com'], workPattern: '^/(?:kr/)?title/[0-9]+$', imageHosts: ['*.nflxso.net', 'assets.nflxext.com'] }
  }
};
