/* Progressive enhancement: the complete collection and links work without JavaScript. */
(() => {
  const filters = document.querySelector('.filters');
  const cards = [...document.querySelectorAll('.work-card')];
  const buttons = [...document.querySelectorAll('[data-filter]')];
  const empty = document.querySelector('#empty-state');
  const status = document.querySelector('#filter-status');
  const types = new Set(buttons.map(button => button.dataset.filter));
  function filter(type, updateUrl = true) {
    if (!types.has(type)) type = 'all';
    let shown = 0;
    cards.forEach(card => {card.hidden = type !== 'all' && card.dataset.type !== type; if (!card.hidden) shown++;});
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === type)));
    empty.hidden = shown !== 0;
    status.textContent = `显示 ${shown} 件作品`;
    if (updateUrl) {
      const url = new URL(location.href);
      if (type === 'all') url.searchParams.delete('type'); else url.searchParams.set('type', type);
      history.replaceState(null, '', url);
    }
  }
  filters.hidden = false;
  buttons.forEach(button => button.addEventListener('click', () => filter(button.dataset.filter)));
  document.querySelector('#reset-filter').addEventListener('click', () => filter('all'));
  addEventListener('popstate', () => filter(new URL(location.href).searchParams.get('type') || 'all', false));
  filter(new URL(location.href).searchParams.get('type') || 'all', false);

  const dialog = document.querySelector('#video-dialog');
  const player = document.querySelector('#video-player');
  const playerStatus = document.querySelector('#video-status');
  let opener;
  function close() {dialog.close();}
  function openVideo(link) {
    opener = link;
    document.querySelector('#video-title').textContent = link.dataset.title;
    document.querySelector('#video-direct').href = link.href;
    player.poster = link.dataset.poster;
    player.src = link.href;
    playerStatus.textContent = '正在加载视频…';
    dialog.showModal();
    player.focus({preventScroll:true});
    player.play().catch(() => {if (!player.error) playerStatus.textContent = '点击播放按钮开始观看。';});
  }
  document.querySelectorAll('[data-video]').forEach(link => link.addEventListener('click', event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || !dialog.showModal) return;
    event.preventDefault();
    openVideo(link);
  }));
  document.querySelector('#close-video').addEventListener('click', close);
  dialog.addEventListener('click', event => {
    const bounds = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom)) close();
  });
  dialog.addEventListener('close', () => {
    player.pause();player.removeAttribute('src');player.load();playerStatus.textContent = '';
    if (opener?.isConnected) opener.focus({preventScroll:true});
  });
  player.addEventListener('playing', () => {playerStatus.textContent = '';});
  player.addEventListener('canplay', () => {if (player.paused) playerStatus.textContent = '点击播放按钮开始观看。';});
  player.addEventListener('waiting', () => {if (dialog.open) playerStatus.textContent = '正在缓冲…';});
  player.addEventListener('error', () => {if (dialog.open) playerStatus.textContent = '视频暂时无法加载，请重试或单独打开。';});
  document.querySelector('#back-top').addEventListener('click', event => {event.preventDefault();window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});});
})();
