import { icon } from '../../components/icons.js';
import { avatar, btn, empty, head, link, para, tag } from '../../components/ui.js';
import { api, list } from '../../core/api.js';
import { date, enc, esc } from '../../core/format.js';
import { isOwner, pages, state, teamUrl } from '../../core/state.js';

pages.experiences = async () => {
  const [items, bookmarks] = await Promise.all([
    list(teamUrl('/experiences')),
    list(`/me/bookmarks?teamId=${enc(state.team.id)}`),
  ]);
  state.data.experiences = items;
  state.data.bookmarks = new Set(bookmarks.map((b) => b.experienceId || b.id));
  return (
    head(
      '前辈经验',
      '不只看最后的成果，也看看当时的选择、卡点和调整。',
      btn(icon('plus') + '分享一次经历', 'create-experience', '', 'primary'),
    ) +
    `<div class="callout">${icon('people')}<div>先看前辈当时的基础与资源，再判断经历是否适合自己。让真实的尝试成为后来者的路标。</div></div><div class="toolbar"><div class="filters"><button class="filter active" data-action="experience-filter" data-id="all">全部经验</button><button class="filter" data-action="experience-filter" data-id="bookmarked">我的收藏</button></div><input class="input local-search" data-filter="experiences" aria-label="搜索经验" placeholder="搜索经验标题、作者…"></div><div class="grid3" id="experienceCards">${experienceCards(items)}</div>`
  );
};

function experienceCards(items) {
  return items.length
    ? items
        .map(
          (e, i) =>
            `<article class="panel"><div class="mentorcover" style="background:${['#6d92dc', '#5ba88a', '#9a83c2'][i % 3]}"></div><div class="mentorcard"><div class="flex">${avatar(e.author, ['mint', 'gold', 'pink'][i % 3])}<div><h3>${esc(e.author)}</h3><span class="small">${date(e.createdAt, { year: 'numeric' })}</span></div><h2 class="mt16">${esc(e.title)}</h2><div class="quote text-clamp">${esc(e.startingPoint || e.summary || '阅读这段经历，了解当时的基础、尝试和调整。')}</div><div class="flex wrap mb16">${(e.tags || []).map((t) => tag(t)).join('')}${state.data.bookmarks.has(e.id) ? tag('已收藏', 'orange') : ''}</div>${link('阅读完整经历 ' + icon('arrow'), 'experience/' + enc(e.id), 'btn wfull')}</div></article>`,
        )
        .join('')
    : `<section class="panel" style="grid-column:1/-1">${empty('等待第一段真实经历', '从一次阅读、复现或组会中的调整开始，把有用的经验留下来。', btn('分享我的经历', 'create-experience', '', 'primary'), 'people')}</section>`;
}

pages.experience = async (id) => {
  const e = await api(`/experiences/${enc(id)}`);
  state.data.experience = e;
  const bookmarks = await list(`/me/bookmarks?teamId=${enc(state.team.id)}`);
  const saved = bookmarks.some((b) => (b.experienceId || b.id) === id);
  const editable = e.authorId === state.user.id || isOwner();
  return (
    link(icon('back') + '返回前辈经验', 'experiences', 'textbutton mb16') +
    head(
      e.title,
      `${e.author} · ${date(e.createdAt, { year: 'numeric' })}`,
      `${editable ? btn('编辑经验', 'edit-experience', id) : ''}${btn(icon('heart') + (saved ? '已收藏 · 取消' : '收藏经验'), saved ? 'unbookmark' : 'bookmark', id)}`,
    ) +
    `<div class="grid2"><article class="panel padded"><div class="flex wrap mb16">${(e.tags || []).map((t) => tag(t, 'blue')).join('')}</div><h2>我当时的起点</h2><div class="rich-section">${para(e.startingPoint)}</div><div class="divider"></div><h2>经历、调整与建议</h2><div class="rich-section">${para(e.content)}</div></article><aside><section class="panel padded"><div class="flex">${avatar(e.author, 'mint')}<div><h3>${esc(e.author)}</h3><p class="small">经验贡献者</p></div></div><div class="divider"></div><h3>结合自己的条件判断</h3><p class="section-note mt16">经验保留了当时的基础与限制。复用前，先确认资源、研究目标与当前情境是否相同。</p>${btn('我也想分享', 'create-experience', '', 'mt16')}</section></aside></div>`
  );
};
export { experienceCards };
