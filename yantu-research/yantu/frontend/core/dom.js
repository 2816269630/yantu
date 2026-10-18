const $ = (s, root = document) => root.querySelector(s);

const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export { $, $$ };
