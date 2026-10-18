
/* =====================================================================
   JsonUI Agent View: demo script, 3D office and live side panel
   ===================================================================== */

/* ---------- demo script: one 84-second loop of a JsonUI project ---------- */
const LOOP = 84;
const START_AT = 24;
const BASE_CLOCK = 14 * 3600 + 20 * 60;

const ROOMS = [
  { id: 'shop', name: 'shop-app/', path: '~/work/shop-app', x0: -9.6, x1: 2.6, z0: -5.0, z1: 4.2, floor: '--floor-a', back: 3.9, left: 3.9 },
  { id: 'cli', name: 'jsonui-cli/', path: '~/resource/jsonui-cli', x0: 3.1, x1: 10.2, z0: -5.0, z1: -0.25, floor: '--floor-b', back: 3.9, left: 0.55 },
  { id: 'doc', name: 'JsonUIDocument/', path: '~/resource/JsonUIDocument', x0: 3.1, x1: 10.2, z0: 0.25, z1: 4.2, floor: '--floor-c', back: 0.55, left: 0.55 },
];
/* One room per project folder; a project can hold any number of sessions. */
const PROJECT = Object.fromEntries(ROOMS.map((r) => [r.id, r]));
const SESSIONS = [
  { id: 'a0', project: 'shop', robots: ['a0', 'a3', 'a5', 'a2', 'a7'] },
  { id: 'b4', project: 'shop', robots: ['b4', 'e6', 'f2'] },
  { id: 'd8', project: 'shop', robots: ['d8'] },
  { id: '4f', project: 'cli', robots: ['4f'] },
  { id: '7c', project: 'cli', robots: ['7c'] },
  { id: 'c9', project: 'doc', robots: ['c9'] },
  { id: 'e1', project: 'doc', robots: ['e1'] },
].map((s) => ({ ...s, room: PROJECT[s.project].name }));
const ROBOT_DEFS = [
  { id: 'a0', role: 'main', agent: 'セッション a07c…', pos: [0.7, -2.5], ry: 0.3, furnished: true,
    plan: [[0, 'reading', 'Read docs/screens/json/cart.spec.json'], [12, 'typing', 'TaskCreate #7・#8'], [20, 'idle', 'サブエージェントの報告待ち'], [62, 'reading', 'a3 の報告を確認'], [70, 'typing', 'TaskList で残りを確認'], [76, 'idle', 'サブエージェントの報告待ち']] },
  { id: 'a3', role: 'define', agent: 'jsonui-define', pos: [-6.3, -3.1], ry: 0.55, furnished: true,
    plan: [[0, 'reading', 'Read home.spec.json（参考）'], [5, 'typing', 'Write docs/screens/json/login.spec.json'], [62, 'done', 'Login の spec を書き終えた'], [66, 'idle', '待機'], [70, 'reading', 'doc_validate_spec login'], [76, 'idle', '待機']] },
  { id: 'a5', role: 'implement', agent: 'jsonui-implement', pos: [-2.7, -2.7], ry: 0.5, furnished: true,
    plan: [[0, 'reading', 'Read docs/screens/json/home.spec.json'], [6, 'typing', 'Edit docs/screens/layouts/home.json'], [40, 'command', 'Bash jui build'], [48, 'typing', 'Edit HomeViewModel.swift'], [70, 'command', 'jui_verify home.spec.json'], [76, 'done', 'Home の実装が終わった'], [80, 'idle', '待機']] },
  { id: 'a2', role: 'test', agent: 'jsonui-test', pos: [-7.3, 1.2], ry: 0.75,
    plan: [[0, 'idle', '待機'], [10, 'command', 'test_validate cart.test.json'], [18, 'phone', 'xcodebuild test（iPhone 16）'], [60, 'done', 'Cart のテスト 8/8 通過'], [66, 'idle', '待機']] },
  { id: 'a7', role: 'navigation', agent: 'jsonui-navigation-ios', walk: true },
  { id: 'b4', role: 'main', agent: 'セッション b47e…', pos: [-0.4, 3.5], ry: 0.15, furnished: true,
    plan: [[0, 'typing', 'TaskCreate #5'], [6, 'idle', 'サブエージェントの報告待ち'], [70, 'reading', 'e6 の報告を確認'], [74, 'idle', 'サブエージェントの報告待ち']] },
  { id: 'e6', role: 'define', agent: 'jsonui-define', pos: [-2.9, 3.4], ry: 0.25, furnished: true,
    plan: [[0, 'reading', 'Read login.spec.json（参考）'], [8, 'typing', 'Write docs/screens/json/signup.spec.json'], [70, 'done', 'Signup の spec を書き終えた'], [74, 'idle', '待機']] },
  { id: 'f2', role: 'implement', agent: 'jsonui-implement', pos: [-5.3, 3.3], ry: 0.4, furnished: true,
    plan: [[0, 'typing', 'Edit docs/screens/layouts/product-detail.json'], [30, 'command', 'Bash jui build'], [36, 'typing', 'Edit ProductDetailViewModel.swift'], [74, 'command', 'jui_verify product-detail.spec.json'], [78, 'done', 'ProductDetail の実装が終わった'], [82, 'idle', '待機']] },
  { id: 'd8', role: 'main', agent: 'セッション d8a5…', pos: [-8.5, -3.5], ry: 0.6, furnished: true,
    plan: [[0, 'idle', '待機（次の指示待ち）'], [34, 'thinking', '考え中'], [50, 'idle', '待機（次の指示待ち）']] },
  { id: '4f', role: 'main', agent: 'セッション 4f2b…', pos: [6.0, -2.9], ry: 0.05, furnished: true,
    plan: [[0, 'command', 'Bash jui build --ios-only'], [22, 'done', 'ビルド完了'], [26, 'idle', '待機'], [38, 'reading', 'Read jui_cli/commands/hotload_cmd.py'], [44, 'command', 'Bash pip install aiohttp watchdog'], [47, 'typing', 'Edit jui_cli/commands/viz_cmd.py'], [78, 'reading', '差分を確認']] },
  { id: '7c', role: 'main', agent: 'セッション 7c3f…', pos: [8.9, -2.6], ry: -0.15, furnished: true,
    plan: [[0, 'typing', 'Edit src/reporter/progress.ts'], [30, 'command', 'Bash npm test -- --progress'], [36, 'typing', 'Edit src/cli/run.ts'], [60, 'command', 'Bash npm test'], [66, 'reading', 'テスト結果を確認']] },
  { id: 'c9', role: 'main', agent: 'セッション c91e…', pos: [6.4, 2.0], ry: 0.1, furnished: true,
    plan: [[0, 'reading', 'Read docs/screens/json/spec-anatomy.spec.json'], [38, 'command', 'Bash jsonui-doc generate html'], [52, 'done', 'HTML を生成した'], [56, 'idle', '待機']] },
  { id: 'e1', role: 'main', agent: 'セッション e1d4…', pos: [8.7, 2.6], ry: -0.1, furnished: true,
    plan: [[0, 'reading', 'Read component-detail.spec.json（参考）'], [20, 'typing', 'Write docs/screens/json/attribute-reference.spec.json'], [78, 'done', '属性リファレンスの spec を書き終えた'], [82, 'idle', '待機']] },
];
const DEF = Object.fromEntries(ROBOT_DEFS.map((d) => [d.id, d]));
const SESSION_OF = Object.fromEntries(SESSIONS.flatMap((s) => s.robots.map((id) => [id, s.id])));
const PROJECT_OF = Object.fromEntries(SESSIONS.map((s) => [s.id, s.project]));
const projectOfRobot = (id) => PROJECT_OF[SESSION_OF[id]];
const SESSION_UUID = { a0: 'a07c09fe-2f17-530c-add4-737ff77c3934', b4: 'b47e2d19-6c3a-4f80-9e25-1d8b7c4a0f62', d8: 'd8a51e07-2c4b-4e19-8f3a-6b0d9c2e7a14', '4f': '4f2b91c0-8d3e-4a51-9b7e-0c6d2a5e8f13', '7c': '7c3f5a92-1e8d-4b06-a7c4-9d2e0f6b3a81', c9: 'c91e7a44-5b20-4f6d-8e19-3a7b2c0d9e55', e1: 'e1d4b8f3-7a29-4c51-b0e6-2f9a8c3d1e70' };
const AGENT_ID = { a3: 'a3f19c2e8b7d4a601', a5: 'a5c08e1b9f2d7a3e4', a2: 'a2b7d40c6e9f1a835', a7: 'a7e2c91d0b8f6a4c3', e6: 'e6d93a0f4c2b7e815', f2: 'f2a61c8e0d9b3f574' };
const CWD = Object.fromEntries(SESSIONS.map((s) => [s.id, PROJECT[s.project].path.replace('~', '/Users/you')]));
const WALK = { points: [[1.0, 1.5], [-2.7, -1.2], [-6.1, -1.5], [-4.0, 1.6]], speed: 1.05, pause: 2.2 };

/* Every screen of the demo project in board order: [key, screen name, 表示名, file stem]. */
const SCREENS = [
  ['onboarding', 'Onboarding', 'はじめに', 'onboarding'],
  ['login', 'Login', 'ログイン', 'login'],
  ['signup', 'Signup', '新規登録', 'signup'],
  ['reset', 'PasswordReset', 'パスワード再設定', 'password-reset'],
  ['home', 'Home', 'ホーム', 'home'],
  ['search', 'Search', '検索', 'search'],
  ['filter', 'FilterSheet', '絞り込み', 'filter-sheet'],
  ['list', 'ProductList', '商品一覧', 'product-list'],
  ['detail', 'ProductDetail', '商品詳細', 'product-detail'],
  ['reviews', 'Reviews', 'レビュー', 'reviews'],
  ['favorites', 'Favorites', 'お気に入り', 'favorites'],
  ['cart', 'Cart', 'カート', 'cart'],
  ['coupons', 'Coupons', 'クーポン', 'coupons'],
  ['checkout', 'Checkout', '購入手続き', 'checkout'],
  ['complete', 'OrderComplete', '注文完了', 'order-complete'],
  ['orders', 'OrderHistory', '注文履歴', 'order-history'],
  ['order', 'OrderDetail', '注文詳細', 'order-detail'],
  ['mypage', 'MyPage', 'マイページ', 'my-page'],
  ['address', 'AddressList', 'お届け先', 'address-list'],
  ['addressEdit', 'AddressEdit', 'お届け先の編集', 'address-edit'],
  ['payment', 'PaymentMethods', '支払い方法', 'payment-methods'],
  ['notices', 'Notifications', 'お知らせ', 'notifications'],
  ['settings', 'Settings', '設定', 'settings'],
  ['help', 'Help', 'ヘルプ', 'help'],
  ['top', 'Top', 'トップ', 'top', 'doc'],
  ['start', 'GettingStarted', 'はじめかた', 'getting-started', 'doc'],
  ['components', 'ComponentList', 'コンポーネント一覧', 'component-list', 'doc'],
  ['component', 'ComponentDetail', 'コンポーネント詳細', 'component-detail', 'doc'],
  ['attrs', 'AttributeReference', '属性リファレンス', 'attribute-reference', 'doc'],
  ['anatomy', 'SpecAnatomy', 'spec の構造', 'spec-anatomy', 'doc'],
];
/* The spec files shown on the whiteboard (demo content in the screen_spec format). Counted items per section:
   structure.components, stateManagement.uiVariables, dataFlow.viewModel.methods, userActions, transitions
   and branchContracts branches. */
const SPEC_DOCS = {
  login: {
    metadata: { name: 'Login', displayName: 'ログイン', description: 'メールアドレスとパスワードでログインする', platforms: ['ios', 'android', 'web'], layoutFile: 'login', createdAt: '2026-10-17' },
    components: [['View', 'login_root', '画面全体のコンテナ'], ['Label', 'title_label', '画面タイトル「ログイン」'], ['TextField', 'email_input', 'メールアドレス入力'], ['TextField', 'password_input', 'パスワード入力（伏せ字）'], ['Label', 'error_label', '入力エラーと認証エラー'], ['Button', 'login_button', 'ログインを実行'], ['Indicator', 'loading_indicator', '通信中の表示'], ['Button', 'forgot_button', 'パスワード再設定へ'], ['Button', 'signup_button', '新規登録へ']],
    layoutChildren: ['title_label', 'email_input', 'password_input', 'error_label', 'login_button', 'loading_indicator', 'forgot_button', 'signup_button'],
    uiVariables: [['email', 'String', '""'], ['password', 'String', '""'], ['isLoading', 'Bool', 'false'], ['errorMessage', 'String?', 'null']],
    eventHandlers: [['onLoginTap', '入力を検証して login() を呼ぶ'], ['onSignupTap', 'Signup 画面へ遷移']],
    vmMethods: ['login()', 'validateEmail(_:)', 'validatePassword(_:)', 'clearError()', 'openSignup()'],
    vmVars: ['email', 'password', 'isLoading', 'errorMessage'],
    repositories: ['AuthRepository'],
    apis: [['postLogin', 'POST', '/auth/login']],
    userActions: [['ログインボタンをタップ', 'onLoginTap → login()'], ['パスワードを忘れたをタップ', '再設定画面へ遷移'], ['新規登録をタップ', 'onSignupTap']],
    transitions: [['login() 成功', 'Home'], ['signup_button をタップ', 'Signup']],
    branches: [['login', 'email が空', 'error_label に「メールアドレスを入力」'], ['login', 'password が 8 文字未満', 'error_label に「8 文字以上」'], ['login', 'API が 401', 'error_label に認証エラー'], ['login', 'API が 200', 'Home へ遷移']],
  },
  home: {
    metadata: { name: 'Home', displayName: 'ホーム', description: 'おすすめとカテゴリを並べ、カートと検索の入口になる', platforms: ['ios', 'android', 'web'], layoutFile: 'home', createdAt: '2026-10-12' },
    components: [['SafeAreaView', 'home_root', '画面全体'], ['View', 'header_view', 'ヘッダー'], ['Label', 'greeting_label', 'あいさつ文'], ['Button', 'cart_button', 'カートへ'], ['Label', 'cart_badge', 'カート内の件数'], ['TextField', 'search_input', '商品検索'], ['Collection', 'banner_collection', 'キャンペーンバナー'], ['Label', 'category_title', 'カテゴリ見出し'], ['Collection', 'category_collection', 'カテゴリ一覧'], ['Label', 'recommend_title', 'おすすめ見出し'], ['Collection', 'recommend_collection', 'おすすめ商品'], ['Indicator', 'loading_indicator', '読み込み中']],
    layoutChildren: ['header_view', 'search_input', 'banner_collection', 'category_title', 'category_collection', 'recommend_title', 'recommend_collection', 'loading_indicator'],
    uiVariables: [['userName', 'String', '""'], ['cartCount', 'Int', '0'], ['searchText', 'String', '""'], ['isLoading', 'Bool', 'true'], ['banners', '[Banner]', '[]']],
    eventHandlers: [['onCartTap', 'Cart 画面へ'], ['onSearchSubmit', '検索結果へ'], ['onProductTap', '商品詳細へ']],
    vmMethods: ['onAppear()', 'loadHome()', 'refresh()', 'openCart()', 'search(_:)', 'openProduct(_:)'],
    vmVars: ['userName', 'cartCount', 'banners', 'categories', 'recommends', 'isLoading'],
    repositories: ['HomeRepository', 'CartRepository'],
    apis: [['getHome', 'GET', '/home'], ['getCartSummary', 'GET', '/cart/summary']],
    userActions: [['カートボタンをタップ', 'onCartTap → openCart()'], ['検索を確定', 'onSearchSubmit → search(_:)'], ['おすすめ商品をタップ', 'onProductTap → openProduct(_:)'], ['引っ張って更新', 'refresh()']],
    transitions: [['openCart()', 'Cart'], ['openProduct(_:)', 'ProductDetail']],
    branches: [['loadHome', 'API 成功', 'banners と recommends を表示'], ['loadHome', 'API 失敗', 'エラーと再試行ボタンを表示'], ['openCart', 'cartCount == 0', '空のカートとして開く']],
  },
  cart: {
    metadata: { name: 'Cart', displayName: 'カート', description: 'カートの中身を確認して、クーポンを当てて購入へ進む', platforms: ['ios', 'android', 'web'], layoutFile: 'cart', createdAt: '2026-10-08' },
    components: [['SafeAreaView', 'cart_root', '画面全体'], ['Label', 'title_label', '画面タイトル「カート」'], ['Collection', 'cart_list', 'カート内の商品（cart_item）'], ['Label', 'empty_label', 'カートが空のときの案内'], ['Label', 'stock_warning', '在庫切れの警告'], ['TextField', 'coupon_input', 'クーポンコード'], ['Button', 'coupon_apply', 'クーポンを適用'], ['Label', 'coupon_error', 'クーポンのエラー'], ['Label', 'total_label', '合計金額'], ['Button', 'checkout_button', '購入する']],
    layoutChildren: ['title_label', 'cart_list', 'empty_label', 'stock_warning', 'coupon_input', 'coupon_apply', 'coupon_error', 'total_label', 'checkout_button'],
    uiVariables: [['items', '[CartItem]', '[]'], ['isEmpty', 'Bool', 'true'], ['couponCode', 'String', '""'], ['couponError', 'String?', 'null'], ['total', 'Int', '0'], ['canCheckout', 'Bool', 'false']],
    eventHandlers: [['onQuantityChange', '数量を変更'], ['onApplyCoupon', 'クーポンを適用'], ['onCheckoutTap', '購入へ進む']],
    vmMethods: ['loadCart()', 'changeQuantity(_:qty:)', 'applyCoupon(_:)', 'removeItem(_:)', 'recalcTotal()', 'checkout()', 'placeOrder()'],
    vmVars: ['items', 'isEmpty', 'couponCode', 'couponError', 'total', 'canCheckout'],
    repositories: ['CartRepository', 'OrderRepository'],
    apis: [['getCart', 'GET', '/cart'], ['postCoupon', 'POST', '/cart/coupon'], ['postOrder', 'POST', '/orders']],
    userActions: [['数量を変更', 'onQuantityChange → changeQuantity'], ['クーポンを適用', 'onApplyCoupon → applyCoupon'], ['商品を削除', 'removeItem'], ['購入するをタップ', 'onCheckoutTap → checkout()'], ['購入を確定', 'placeOrder()']],
    transitions: [['checkout()（未ログイン）', 'Login'], ['placeOrder() 成功', 'OrderComplete'], ['商品をタップ', 'ProductDetail']],
    branches: [['loadCart', 'items.count > 0', 'cart_list を表示'], ['changeQuantity', 'qty == 0', 'その行を消す'], ['loadCart', 'isEmpty == true', 'checkout_button を無効にする'], ['applyCoupon', 'valid', 'discount_label を表示'], ['applyCoupon', 'expired', 'coupon_error を表示'], ['loadCart', 'item.stock == 0', 'stock_warning を表示'], ['checkout', '未ログイン', 'Login へ遷移'], ['placeOrder', 'success', 'OrderComplete へ遷移']],
  },
  list: {
    metadata: { name: 'ProductList', displayName: '商品一覧', description: '商品を一覧で見せ、並び替えと絞り込みができる', platforms: ['ios', 'android', 'web'], layoutFile: 'product-list', createdAt: '2026-10-02' },
    components: [['SafeAreaView', 'list_root', '画面全体'], ['TextField', 'search_input', '絞り込み'], ['Segment', 'sort_segment', '並び替え'], ['Collection', 'product_collection', '商品一覧（product_cell）'], ['Label', 'result_count', '件数'], ['Indicator', 'loading_indicator', '読み込み中'], ['Label', 'empty_label', '該当なし'], ['Button', 'filter_button', '絞り込み条件']],
    layoutChildren: ['search_input', 'sort_segment', 'filter_button', 'result_count', 'product_collection', 'loading_indicator', 'empty_label'],
    uiVariables: [['products', '[Product]', '[]'], ['query', 'String', '""'], ['sort', 'SortOrder', '.popular'], ['isLoading', 'Bool', 'true']],
    eventHandlers: [['onSortChange', '並び替えを変更'], ['onProductTap', '商品詳細へ']],
    vmMethods: ['load()', 'loadMore()', 'changeSort(_:)', 'search(_:)', 'openProduct(_:)'],
    vmVars: ['products', 'query', 'sort', 'isLoading'],
    repositories: ['ProductRepository'],
    apis: [['listProducts', 'GET', '/products']],
    userActions: [['並び替えを変更', 'onSortChange → changeSort'], ['最後までスクロール', 'loadMore()'], ['商品をタップ', 'onProductTap → openProduct']],
    transitions: [['openProduct(_:)', 'ProductDetail'], ['filter_button をタップ', 'FilterSheet']],
    branches: [['load', '結果が 0 件', 'empty_label を表示'], ['load', 'API 失敗', 'エラーを表示'], ['loadMore', '最終ページ', '読み込みを止める'], ['changeSort', 'price', '価格順に並べる'], ['search', 'query が空', '全件を表示']],
  },
};
/* The other screens, written more compactly: components are 'Type id 説明' separated by '|'. */
function doc(key, description, createdAt, comps, r) {
  const [, name, displayName, stem, project] = SCREENS.find((x) => x[0] === key);
  const components = comps.split('|').map((x) => { const [type, id, ...rest] = x.trim().split(' '); return [type, id, rest.join(' ')]; });
  return {
    metadata: { name, displayName, description, platforms: project === 'doc' ? ['web'] : ['ios', 'android', 'web'], layoutFile: stem, createdAt },
    components, layoutChildren: components.slice(1).map((c) => c[1]),
    uiVariables: r.vars, eventHandlers: r.handlers, vmMethods: r.methods, vmVars: r.vars.map((v) => v[0]),
    repositories: r.repos, apis: r.apis, userActions: r.actions, transitions: r.transitions, branches: r.branches,
  };
}
Object.assign(SPEC_DOCS, {
  onboarding: doc('onboarding', 'アプリの使い方を 3 枚のスライドで紹介し、通知の許可を求める', '2026-09-20',
    'SafeAreaView onboarding_root 画面全体|Collection slide_pager 紹介スライド（3 枚）|View page_dots 今のページ|Button next_button 次へ|Button skip_button スキップ|Button start_button はじめる',
    { vars: [['page', 'Int', '0'], ['isLastPage', 'Bool', 'false']], handlers: [['onNextTap', '次のスライドへ'], ['onStartTap', '通知の許可を求めてホームへ']],
      methods: ['next()', 'skip()', 'start()', 'requestNotification()'], repos: ['SettingsRepository'], apis: [],
      actions: [['次へをタップ', 'onNextTap → next()'], ['スキップをタップ', 'skip()'], ['はじめるをタップ', 'onStartTap → start()']],
      transitions: [['start()', 'Home'], ['skip()', 'Home']],
      branches: [['next', '最後のスライド', 'start_button を表示'], ['start', '通知を拒否', 'そのまま Home へ']] }),
  signup: doc('signup', 'メールアドレスとパスワードでアカウントを作る', '2026-10-17',
    'SafeAreaView signup_root 画面全体|Label title_label 画面タイトル「新規登録」|TextField name_input お名前|TextField email_input メールアドレス|TextField password_input パスワード（8 文字以上）|CheckBox terms_check 利用規約に同意|Label error_label 入力エラー|Button signup_button 登録する|Button login_link ログインへ戻る|Indicator loading_indicator 通信中の表示',
    { vars: [['name', 'String', '""'], ['email', 'String', '""'], ['password', 'String', '""'], ['agreed', 'Bool', 'false'], ['errorMessage', 'String?', 'null'], ['isLoading', 'Bool', 'false']],
      handlers: [['onSignupTap', '入力を検証して signup() を呼ぶ'], ['onTermsToggle', '同意を切り替える']],
      methods: ['signup()', 'validate()', 'toggleTerms()', 'openLogin()'], repos: ['AuthRepository'], apis: [['postSignup', 'POST', '/auth/signup']],
      actions: [['登録するをタップ', 'onSignupTap → signup()'], ['利用規約に同意', 'onTermsToggle → toggleTerms()'], ['ログインへ戻るをタップ', 'openLogin()']],
      transitions: [['signup() 成功', 'Home'], ['login_link をタップ', 'Login']],
      branches: [['signup', '規約に未同意', 'signup_button を無効にする'], ['signup', 'email が登録済み', 'error_label に「登録済み」'], ['signup', 'password が 8 文字未満', 'error_label に「8 文字以上」'], ['signup', 'API が 201', 'Home へ遷移']] }),
  search: doc('search', 'キーワードで商品を探し、履歴と候補を出す', '2026-09-28',
    'SafeAreaView search_root 画面全体|TextField search_input キーワード|Button cancel_button キャンセル|Collection history_list 検索履歴|Collection suggest_list 候補|Button clear_history 履歴を消す',
    { vars: [['query', 'String', '""'], ['history', '[String]', '[]'], ['suggestions', '[String]', '[]']], handlers: [['onSubmit', '検索を確定'], ['onClearHistory', '履歴を消す']],
      methods: ['loadHistory()', 'suggest(_:)', 'submit()', 'clearHistory()'], repos: ['SearchRepository'], apis: [['getSuggestions', 'GET', '/search/suggest']],
      actions: [['キーワードを入力', 'suggest(_:)'], ['検索を確定', 'onSubmit → submit()'], ['履歴を消すをタップ', 'onClearHistory → clearHistory()']],
      transitions: [['submit()', 'ProductList'], ['cancel_button をタップ', 'Home']],
      branches: [['suggest', 'query が空', '履歴を表示'], ['suggest', '候補 0 件', '「候補なし」を表示'], ['submit', 'query が空', '何もしない']] }),
  filter: doc('filter', '価格・カテゴリ・在庫で一覧を絞り込むシート', '2026-09-30',
    'View filter_root シート全体|Label title_label 見出し「絞り込み」|SelectBox category_select カテゴリ|View price_range 価格の範囲|Switch stock_switch 在庫ありのみ|Button reset_button リセット|Button apply_button 適用する',
    { vars: [['category', 'String?', 'null'], ['minPrice', 'Int', '0'], ['maxPrice', 'Int', '50000'], ['inStockOnly', 'Bool', 'false']], handlers: [['onApplyTap', '条件を返して閉じる'], ['onResetTap', '条件を初期値に戻す']],
      methods: ['apply()', 'reset()', 'setPrice(min:max:)'], repos: ['CategoryRepository'], apis: [['listCategories', 'GET', '/categories']],
      actions: [['適用するをタップ', 'onApplyTap → apply()'], ['リセットをタップ', 'onResetTap → reset()']],
      transitions: [['apply()', 'ProductList']],
      branches: [['apply', 'minPrice > maxPrice', '価格を入れ替える'], ['reset', '—', '全条件を初期値に戻す']] }),
  detail: doc('detail', '商品の写真・価格・在庫を見せて、カートに入れる', '2026-10-14',
    'SafeAreaView detail_root 画面全体|Image product_image 商品写真|Label name_label 商品名|Label price_label 価格|Label stock_label 在庫の表示|Segment size_segment サイズの選択|Button add_cart_button カートに入れる|Button favorite_button お気に入り|Label review_summary 評価の平均と件数|Button reviews_button レビューを見る|Indicator loading_indicator 読み込み中',
    { vars: [['product', 'Product?', 'null'], ['size', 'Int', '-1'], ['isFavorite', 'Bool', 'false'], ['canAddToCart', 'Bool', 'false'], ['isLoading', 'Bool', 'true']],
      handlers: [['onAddCartTap', 'カートに追加'], ['onFavoriteTap', 'お気に入りを切り替える'], ['onSizeChange', 'サイズを選ぶ']],
      methods: ['onAppear()', 'loadProduct()', 'selectSize(_:)', 'addToCart()', 'toggleFavorite()', 'openReviews()'], repos: ['ProductRepository', 'CartRepository', 'FavoriteRepository'],
      apis: [['getProduct', 'GET', '/products/{id}'], ['postCartItem', 'POST', '/cart/items'], ['putFavorite', 'PUT', '/favorites/{id}']],
      actions: [['サイズを選ぶ', 'onSizeChange → selectSize(_:)'], ['カートに入れるをタップ', 'onAddCartTap → addToCart()'], ['お気に入りをタップ', 'onFavoriteTap → toggleFavorite()'], ['レビューを見るをタップ', 'openReviews()']],
      transitions: [['addToCart() 成功', 'Cart'], ['openReviews()', 'Reviews']],
      branches: [['loadProduct', 'stock == 0', 'add_cart_button を無効にして在庫切れを表示'], ['addToCart', 'サイズ未選択', 'size_segment を強調'], ['addToCart', 'API 成功', 'Cart へ遷移'], ['toggleFavorite', '未ログイン', 'Login へ遷移']] }),
  reviews: doc('reviews', '商品のレビューを新しい順に見せ、評価で絞り込む', '2026-10-06',
    'SafeAreaView reviews_root 画面全体|Label average_label 平均評価|Segment star_filter 評価で絞り込み|Collection review_list レビュー一覧|Indicator loading_indicator 読み込み中|Label empty_label レビューなし',
    { vars: [['reviews', '[Review]', '[]'], ['stars', 'Int?', 'null'], ['isLoading', 'Bool', 'true']], handlers: [['onStarFilter', '評価で絞り込む']],
      methods: ['load()', 'loadMore()', 'filter(stars:)'], repos: ['ReviewRepository'], apis: [['listReviews', 'GET', '/products/{id}/reviews']],
      actions: [['評価で絞り込む', 'onStarFilter → filter(stars:)'], ['最後までスクロール', 'loadMore()']],
      transitions: [['戻る', 'ProductDetail']],
      branches: [['load', '0 件', 'empty_label を表示'], ['loadMore', '最終ページ', '読み込みを止める'], ['filter', 'stars == nil', '全件を表示']] }),
  favorites: doc('favorites', 'お気に入りに入れた商品を並べ、カートへ移せる', '2026-09-26',
    'SafeAreaView favorites_root 画面全体|Collection favorite_list お気に入り一覧|Label empty_label お気に入りなし|Button edit_button 編集',
    { vars: [['items', '[Product]', '[]'], ['isEditing', 'Bool', 'false']], handlers: [['onRemove', 'お気に入りから外す'], ['onEditTap', '編集モードを切り替える']],
      methods: ['load()', 'remove(_:)', 'moveToCart(_:)'], repos: ['FavoriteRepository'], apis: [['listFavorites', 'GET', '/favorites'], ['deleteFavorite', 'DELETE', '/favorites/{id}']],
      actions: [['商品をタップ', '商品詳細を開く'], ['外すをタップ', 'onRemove → remove(_:)'], ['カートへをタップ', 'moveToCart(_:)']],
      transitions: [['商品をタップ', 'ProductDetail']],
      branches: [['load', '0 件', 'empty_label を表示'], ['remove', '最後の 1 件', 'empty_label に切り替える']] }),
  checkout: doc('checkout', 'お届け先と支払い方法を確かめて注文を確定する', '2026-10-09',
    'SafeAreaView checkout_root 画面全体|Label address_label お届け先|Button address_change お届け先を変更|Label payment_label 支払い方法|Button payment_change 支払い方法を変更|Label subtotal_label 小計|Label shipping_label 送料|Label total_label 合計|Button confirm_button 注文を確定する|Indicator loading_indicator 送信中',
    { vars: [['address', 'Address?', 'null'], ['payment', 'Payment?', 'null'], ['total', 'Int', '0'], ['canConfirm', 'Bool', 'false'], ['isSubmitting', 'Bool', 'false']],
      handlers: [['onConfirmTap', '注文を送る'], ['onChangeAddress', 'お届け先の選択へ']],
      methods: ['load()', 'changeAddress()', 'changePayment()', 'confirm()', 'recalc()'], repos: ['OrderRepository', 'AddressRepository'], apis: [['getCheckout', 'GET', '/checkout'], ['postOrder', 'POST', '/orders']],
      actions: [['注文を確定するをタップ', 'onConfirmTap → confirm()'], ['お届け先を変更', 'onChangeAddress → changeAddress()'], ['支払い方法を変更', 'changePayment()']],
      transitions: [['confirm() 成功', 'OrderComplete'], ['changeAddress()', 'AddressList'], ['changePayment()', 'PaymentMethods']],
      branches: [['load', 'address == nil', 'confirm_button を無効にする'], ['confirm', '在庫切れ', 'エラーを出して Cart へ'], ['confirm', '決済エラー', 'payment_label を強調'], ['confirm', 'success', 'OrderComplete へ遷移']] }),
  complete: doc('complete', '注文番号とお届け予定日を見せる', '2026-10-10',
    'SafeAreaView complete_root 画面全体|Image done_image 完了のイラスト|Label order_number 注文番号|Label delivery_label お届け予定日|Button orders_button 注文履歴を見る|Button home_button 買い物を続ける',
    { vars: [['orderNumber', 'String', '""'], ['deliveryDate', 'String', '""']], handlers: [['onHomeTap', 'ホームへ戻る']],
      methods: ['onAppear()', 'openOrders()', 'backToHome()'], repos: ['OrderRepository'], apis: [['getOrder', 'GET', '/orders/{id}']],
      actions: [['注文履歴を見るをタップ', 'openOrders()'], ['買い物を続けるをタップ', 'onHomeTap → backToHome()']],
      transitions: [['openOrders()', 'OrderHistory'], ['backToHome()', 'Home']],
      branches: [['onAppear', '注文の取得に失敗', '注文番号だけを表示'], ['onAppear', 'success', 'お届け予定日を表示']] }),
  orders: doc('orders', '過去の注文を新しい順に並べる', '2026-10-13',
    'SafeAreaView orders_root 画面全体|Segment period_segment 期間（3 か月 / 1 年 / すべて）|Collection order_list 注文一覧|Label empty_label 注文なし|Indicator loading_indicator 読み込み中',
    { vars: [['orders', '[Order]', '[]'], ['period', 'Int', '0'], ['isLoading', 'Bool', 'true']], handlers: [['onPeriodChange', '期間を変える'], ['onOrderTap', '注文詳細へ']],
      methods: ['load()', 'loadMore()', 'changePeriod(_:)', 'openOrder(_:)'], repos: ['OrderRepository'], apis: [['listOrders', 'GET', '/orders']],
      actions: [['期間を変える', 'onPeriodChange → changePeriod(_:)'], ['注文をタップ', 'onOrderTap → openOrder(_:)'], ['最後までスクロール', 'loadMore()']],
      transitions: [['openOrder(_:)', 'OrderDetail']],
      branches: [['load', '0 件', 'empty_label を表示'], ['loadMore', '最終ページ', '読み込みを止める']] }),
  order: doc('order', '1 件の注文の中身・配送状況・領収書を見せる', '2026-10-16',
    'SafeAreaView order_root 画面全体|Label status_label 配送状況|Collection item_list 注文した商品|Label total_label 合計|Label address_label お届け先|Button receipt_button 領収書|Button cancel_button 注文をキャンセル',
    { vars: [['order', 'Order?', 'null'], ['canCancel', 'Bool', 'false'], ['isLoading', 'Bool', 'true']], handlers: [['onCancelTap', 'キャンセルを確認'], ['onReceiptTap', '領収書を開く']],
      methods: ['load()', 'cancel()', 'openReceipt()'], repos: ['OrderRepository'], apis: [['getOrder', 'GET', '/orders/{id}'], ['postCancel', 'POST', '/orders/{id}/cancel']],
      actions: [['注文をキャンセルをタップ', 'onCancelTap → cancel()'], ['領収書をタップ', 'onReceiptTap → openReceipt()']],
      transitions: [['商品をタップ', 'ProductDetail']],
      branches: [['load', '発送済み', 'cancel_button を隠す'], ['cancel', 'success', 'status_label を「キャンセル済み」に']] }),
  mypage: doc('mypage', '会員情報と各種設定の入口をまとめる', '2026-09-24',
    'SafeAreaView mypage_root 画面全体|Image avatar_image アイコン|Label name_label お名前|Button orders_button 注文履歴|Button favorites_button お気に入り|Button address_button お届け先|Button payment_button 支払い方法|Button settings_button 設定|Button logout_button ログアウト',
    { vars: [['userName', 'String', '""'], ['avatarUrl', 'String?', 'null']], handlers: [['onLogoutTap', 'ログアウトを確認']],
      methods: ['load()', 'logout()', 'open(_:)'], repos: ['UserRepository', 'AuthRepository'], apis: [['getMe', 'GET', '/me'], ['postLogout', 'POST', '/auth/logout']],
      actions: [['各メニューをタップ', 'open(_:)'], ['ログアウトをタップ', 'onLogoutTap → logout()']],
      transitions: [['orders_button をタップ', 'OrderHistory'], ['favorites_button をタップ', 'Favorites'], ['settings_button をタップ', 'Settings'], ['logout() 成功', 'Login']],
      branches: [['logout', '確認でキャンセル', '何もしない'], ['load', '未ログイン', 'Login へ遷移']] }),
  address: doc('address', '登録したお届け先を並べ、既定の 1 件を選ぶ', '2026-10-15',
    'SafeAreaView address_root 画面全体|Collection address_list お届け先一覧|Button add_button お届け先を追加|Label empty_label 登録なし',
    { vars: [['addresses', '[Address]', '[]'], ['selectedId', 'String?', 'null']], handlers: [['onSelect', '既定にする'], ['onAddTap', '追加へ']],
      methods: ['load()', 'select(_:)', 'add()', 'edit(_:)'], repos: ['AddressRepository'], apis: [['listAddresses', 'GET', '/addresses'], ['putDefault', 'PUT', '/addresses/{id}/default']],
      actions: [['お届け先をタップ', 'onSelect → select(_:)'], ['追加をタップ', 'onAddTap → add()'], ['編集をタップ', 'edit(_:)']],
      transitions: [['add()', 'AddressEdit'], ['edit(_:)', 'AddressEdit']],
      branches: [['load', '0 件', 'empty_label と追加ボタンを表示'], ['select', 'Checkout から来た', '選んで Checkout へ戻る']] }),
  settings: doc('settings', '通知・表示・アカウントの設定', '2026-09-22',
    'SafeAreaView settings_root 画面全体|Switch push_switch プッシュ通知|Switch mail_switch メールマガジン|SelectBox theme_select 表示モード|Button help_button ヘルプ|Button delete_button アカウントを削除',
    { vars: [['pushEnabled', 'Bool', 'true'], ['mailEnabled', 'Bool', 'false'], ['theme', 'String', '"system"']], handlers: [['onPushToggle', '通知を切り替える'], ['onDeleteTap', '削除を確認']],
      methods: ['load()', 'togglePush()', 'toggleMail()', 'setTheme(_:)', 'deleteAccount()'], repos: ['SettingsRepository'], apis: [['getSettings', 'GET', '/settings'], ['putSettings', 'PUT', '/settings']],
      actions: [['プッシュ通知を切り替える', 'onPushToggle → togglePush()'], ['表示モードを選ぶ', 'setTheme(_:)'], ['アカウントを削除をタップ', 'onDeleteTap → deleteAccount()']],
      transitions: [['help_button をタップ', 'Help']],
      branches: [['togglePush', 'OS で通知が拒否', '設定アプリへの案内を表示'], ['deleteAccount', 'success', 'Login へ遷移']] }),
});
/* The documentation site (JsonUIDocument) is a JsonUI project of its own. */
Object.assign(SPEC_DOCS, {
  top: doc('top', 'JsonUI の紹介と、各プラットフォームの始め方への入口', '2026-09-10',
    'SafeAreaView top_root 画面全体|Label hero_title 見出し|Label hero_lead 紹介文|Button start_button はじめる|Collection platform_cards iOS・Android・Web の案内|Collection news_list 更新情報',
    { vars: [['news', '[News]', '[]'], ['isLoading', 'Bool', 'true']], handlers: [['onStartTap', 'はじめかたへ']],
      methods: ['load()', 'openStart()', 'openPlatform(_:)'], repos: ['DocsRepository'], apis: [['getNews', 'GET', '/news.json']],
      actions: [['はじめるをタップ', 'onStartTap → openStart()'], ['プラットフォームを選ぶ', 'openPlatform(_:)']],
      transitions: [['openStart()', 'GettingStarted'], ['openPlatform(_:)', 'GettingStarted']],
      branches: [['load', '更新情報が 0 件', 'news_list を隠す'], ['openPlatform', 'web', 'Web の手順を開く']] }),
  start: doc('start', 'インストールから最初の画面を出すまでの手順', '2026-09-12',
    'SafeAreaView start_root 画面全体|Segment platform_tabs iOS・Android・Web の切り替え|Collection step_list 手順|Label code_sample コード例|Button copy_button コピー|Button next_button 次へ',
    { vars: [['platform', 'String', '"ios"'], ['copied', 'Bool', 'false']], handlers: [['onPlatformChange', 'プラットフォームを切り替える'], ['onCopyTap', 'コードをコピー']],
      methods: ['selectPlatform(_:)', 'copyCode()', 'openNext()'], repos: [], apis: [],
      actions: [['プラットフォームを切り替える', 'onPlatformChange → selectPlatform(_:)'], ['コピーをタップ', 'onCopyTap → copyCode()']],
      transitions: [['openNext()', 'ComponentList']],
      branches: [['copyCode', 'success', '「コピーしました」を表示']] }),
  components: doc('components', 'コンポーネントを分類ごとに並べ、詳細ページへつなぐ', '2026-09-18',
    'SafeAreaView list_root 画面全体|TextField filter_input 絞り込み|Segment category_tabs 分類|Collection component_grid コンポーネント一覧|Label empty_label 該当なし',
    { vars: [['query', 'String', '""'], ['category', 'String', '"all"'], ['components', '[Component]', '[]']], handlers: [['onComponentTap', '詳細へ']],
      methods: ['load()', 'filter(_:)', 'selectCategory(_:)', 'openComponent(_:)'], repos: ['DocsRepository'], apis: [['listComponents', 'GET', '/components.json']],
      actions: [['絞り込む', 'filter(_:)'], ['分類を選ぶ', 'selectCategory(_:)'], ['コンポーネントをタップ', 'onComponentTap → openComponent(_:)']],
      transitions: [['openComponent(_:)', 'ComponentDetail']],
      branches: [['filter', '0 件', 'empty_label を表示'], ['selectCategory', 'all', '全件を表示']] }),
  component: doc('component', '1 つのコンポーネントの属性・例・対応プラットフォームを見せる', '2026-10-01',
    'SafeAreaView detail_root 画面全体|Label name_label コンポーネント名|Label summary_label 概要|Collection attr_table 属性の表|Label sample_code JSON の例|Segment preview_tabs プレビューの切り替え',
    { vars: [['component', 'Component?', 'null'], ['preview', 'String', '"ios"']], handlers: [['onAttrTap', '属性リファレンスへ']],
      methods: ['load()', 'selectPreview(_:)', 'openAttribute(_:)'], repos: ['DocsRepository'], apis: [['getComponent', 'GET', '/components/{name}.json']],
      actions: [['属性をタップ', 'onAttrTap → openAttribute(_:)'], ['プレビューを切り替える', 'selectPreview(_:)']],
      transitions: [['openAttribute(_:)', 'AttributeReference']],
      branches: [['load', '存在しない名前', '一覧へ戻す'], ['selectPreview', 'web', 'Web のプレビューを表示']] }),
  attrs: doc('attrs', 'すべての属性を、型・既定値・対応コンポーネントつきで引ける', '2026-10-17',
    'SafeAreaView attr_root 画面全体|TextField search_input 属性名で探す|Segment group_tabs レイアウト・見た目・動き|Collection attr_list 属性一覧|Label type_label 型と既定値|Label platforms_label 対応プラットフォーム|Label empty_label 該当なし',
    { vars: [['query', 'String', '""'], ['group', 'String', '"layout"'], ['attributes', '[Attribute]', '[]'], ['isLoading', 'Bool', 'true']], handlers: [['onSearch', '絞り込む'], ['onAttrTap', '使える部品を表示']],
      methods: ['load()', 'search(_:)', 'selectGroup(_:)', 'openComponent(_:)'], repos: ['DocsRepository'], apis: [['listAttributes', 'GET', '/attributes.json']],
      actions: [['属性名で探す', 'onSearch → search(_:)'], ['分類を選ぶ', 'selectGroup(_:)'], ['対応コンポーネントをタップ', 'openComponent(_:)']],
      transitions: [['openComponent(_:)', 'ComponentDetail']],
      branches: [['search', '0 件', 'empty_label を表示'], ['load', 'SSoT の読み込みに失敗', 'エラーを表示'], ['selectGroup', 'layout', 'レイアウト属性だけ表示']] }),
  anatomy: doc('anatomy', 'screen spec の各セクションを図つきで説明する', '2026-09-28',
    'SafeAreaView anatomy_root 画面全体|Label title_label 見出し|Collection section_list セクションごとの説明|Image diagram_image 構造の図|Label sample_json spec の例',
    { vars: [['sections', '[Section]', '[]']], handlers: [['onSectionTap', 'そのセクションへ移動']],
      methods: ['load()', 'scrollTo(_:)'], repos: ['DocsRepository'], apis: [['getAnatomy', 'GET', '/spec/anatomy.json']],
      actions: [['セクションをタップ', 'onSectionTap → scrollTo(_:)']],
      transitions: [['関連リンクをタップ', 'AttributeReference']],
      branches: [['load', 'success', '図と例を表示']] }),
});
/* Screens nobody works on during the demo keep one state: [phase, share]. Live ones are computed below. */
const STILL = {
  onboarding: ['done'], reset: ['todo'], search: ['done'], filter: ['done'], list: ['done'], reviews: ['impl', 0.3], favorites: ['done'],
  coupons: ['todo'], checkout: ['impl-done'], complete: ['impl', 0.5], orders: ['written'], order: ['writing', 0.55], mypage: ['done'],
  address: ['written'], addressEdit: ['todo'], payment: ['todo'], notices: ['todo'], settings: ['done'], help: ['todo'],
  top: ['done'], start: ['done'], components: ['impl', 0.6], component: ['written'], anatomy: ['done'],
};
const SPECS = SCREENS.map(([id, screen, name, stem, project = 'shop']) => {
  const d = SPEC_DOCS[id] || null;
  return {
    id, screen, name, project, file: `${stem}.spec.json`, doc: d,
    totals: d ? [0, d.components.length, d.uiVariables.length, d.vmMethods.length, d.userActions.length, d.transitions.length, d.branches.length] : [0, 0, 0, 0, 0, 0, 0],
    related: [['Layout', `docs/screens/layouts/${stem}.json`], ['ViewModel', project === 'doc' ? `src/viewmodels/${screen}ViewModel.ts` : `${screen}ViewModel.swift`], ['Test', `tests/screens/${stem}.test.json`]],
  };
});
const SPEC_INDEX = Object.fromEntries(SPECS.map((s, i) => [s.id, i]));
const SCREEN_JA = Object.fromEntries(SCREENS.map((x) => [x[1], x[2]]));

const CASES = [
  { name: '初期表示（商品 3 点）', branch: 'items.count > 0', s: 18, e: 23, steps: ['assert visible cart_list', 'assert count cart_item = 3', 'assert text total_label'] },
  { name: '数量を 0 にすると行が消える', branch: 'changeQuantity: qty == 0', s: 23, e: 28, steps: ['input qty_input_1 "0"', 'tap qty_apply_1', 'assert count cart_item = 2'] },
  { name: '空のカートで購入ボタンが無効', branch: 'isEmpty == true', s: 28, e: 32, steps: ['setMocks cart: empty', 'assert visible empty_label', 'assert disabled checkout_button'] },
  { name: 'クーポン WELCOME10 を適用', branch: 'applyCoupon → valid', s: 32, e: 37, steps: ['input coupon_input "WELCOME10"', 'tap coupon_apply', 'assert text discount_label'] },
  { name: '期限切れクーポンでエラー表示', branch: 'applyCoupon → expired', s: 37, e: 45, failAt: 41, steps: ['input coupon_input "OLD2025"', 'tap coupon_apply', 'assert visible coupon_error'] },
  { name: '在庫切れ商品の警告', branch: 'item.stock == 0', s: 45, e: 50, steps: ['setMocks stock: soldOut', 'assert visible stock_warning', 'assert disabled checkout_button'] },
  { name: '未ログインで購入 → ログイン画面へ', branch: 'checkout → Login', s: 50, e: 55, steps: ['setMocks auth: guest', 'tap checkout_button', 'assert screen Login'] },
  { name: '購入確定で注文完了へ', branch: 'placeOrder → success', s: 55, e: 60, steps: ['tap checkout_button', 'tap confirm_button', 'assert screen OrderComplete'] },
];
/* Task lists are per session (~/.claude/tasks/<list>/), so ids repeat across lists. */
const TASKS = [
  { list: 'a0', id: 1, subject: 'ProductList の画面を実装', activeForm: 'ProductList の画面を実装中', owner: 'a5', spec: 'list', created: -1, start: -1, end: -0.5 },
  { list: 'a0', id: 2, subject: 'Login 画面の spec を書く', activeForm: 'Login の spec を書いています', owner: 'a3', spec: 'login', created: -1, start: 5, end: 62 },
  { list: 'a0', id: 3, subject: 'Home のレイアウトを実装', activeForm: 'Home のレイアウトを実装中', owner: 'a5', spec: 'home', created: -1, start: 6, end: 40.5 },
  { list: 'a0', id: 4, subject: 'Home の ViewModel を実装', activeForm: 'Home の ViewModel を実装中', owner: 'a5', spec: 'home', created: -1, start: 44, end: 76, blockedBy: 3 },
  { list: 'a0', id: 5, subject: 'Cart のテストをシミュレータで流す', activeForm: 'Cart のテストを実行中', owner: 'a2', spec: 'cart', created: -1, start: 13, end: 60 },
  { list: 'a0', id: 6, subject: '文言を strings.json に登録', owner: null, spec: null, created: -1, start: null, end: null },
  { list: 'a0', id: 7, subject: 'Home → Cart の遷移をつなぐ', activeForm: 'Home → Cart の遷移をつないでいます', owner: 'a7', spec: 'home', created: 12, start: 40.5, end: null, blockedBy: 3 },
  { list: 'a0', id: 8, subject: 'jui verify で spec とのズレを確認', activeForm: 'jui verify を実行中', owner: 'a5', spec: 'home', created: 12.4, start: 70, end: 74 },
  { list: 'b4', id: 1, subject: 'Signup 画面の spec を書く', activeForm: 'Signup の spec を書いています', owner: 'e6', spec: 'signup', created: -1, start: 5, end: 70 },
  { list: 'b4', id: 2, subject: 'ProductDetail のレイアウトを実装', activeForm: 'ProductDetail のレイアウトを実装中', owner: 'f2', spec: 'detail', created: -1, start: -1, end: 30.2 },
  { list: 'b4', id: 3, subject: 'ProductDetail の ViewModel を実装', activeForm: 'ProductDetail の ViewModel を実装中', owner: 'f2', spec: 'detail', created: -1, start: 36, end: 78, blockedBy: 2 },
  { list: 'b4', id: 4, subject: 'Signup 画面を実装', owner: null, spec: 'signup', created: -1, start: null, end: null, blockedBy: 1 },
  { list: 'b4', id: 5, subject: 'ProductDetail → Cart の遷移をつなぐ', owner: null, spec: 'detail', created: 2, start: null, end: null, blockedBy: 3 },
  { list: 'd8', id: 1, subject: 'Coupons 画面の spec を書く', owner: null, spec: 'coupons', created: -1, start: null, end: null },
  { list: '4f', id: 1, subject: 'jui build の iOS 出力を直す', activeForm: 'jui build の iOS 出力を直しています', owner: '4f', spec: null, created: -1, start: -1, end: 22 },
  { list: '4f', id: 2, subject: 'jui viz コマンドの雛形を作る', activeForm: 'jui viz の雛形を作っています', owner: '4f', spec: null, created: -1, start: 44, end: null },
  { list: '4f', id: 3, subject: 'フック受信サーバーのテストを書く', owner: null, spec: null, created: -1, start: null, end: null, blockedBy: 2 },
  { list: '7c', id: 1, subject: 'jsonui-test にケースごとの進捗出力を足す', activeForm: '進捗出力を実装中', owner: '7c', spec: null, created: -1, start: -1, end: null },
  { list: '7c', id: 2, subject: 'README に --progress の説明を書く', owner: null, spec: null, created: -1, start: null, end: null, blockedBy: 1 },
  { list: 'c9', id: 1, subject: 'spec の構造ページの HTML を生成', activeForm: 'HTML を生成中', owner: 'c9', spec: 'anatomy', created: -1, start: 0, end: 52 },
  { list: 'c9', id: 2, subject: 'コンポーネント一覧に新しい属性を反映', owner: null, spec: 'components', created: -1, start: null, end: null },
  { list: 'c9', id: 3, subject: '検索ページの文言を直す', owner: 'c9', spec: null, created: -1, start: -1, end: -0.5 },
  { list: 'e1', id: 1, subject: '属性リファレンスの spec を書く', activeForm: '属性リファレンスの spec を書いています', owner: 'e1', spec: 'attrs', created: -1, start: 18, end: 78 },
  { list: 'e1', id: 2, subject: '属性リファレンスを実装', owner: null, spec: 'attrs', created: -1, start: null, end: null, blockedBy: 1 },
];
/* The turns (requester, 10-18): one card per prompt a session received, done at Stop; 4f waits for its pip install
   (p6) while its second turn works. */
TASKS.push(
  { list: 'a0', id: 'turn-1', source: 'turn', turn: 1, subject: 'ホームからカートまでの画面を仕上げて', owner: 'a0', spec: null, created: -1, start: -1, end: null },
  { list: 'b4', id: 'turn-1', source: 'turn', turn: 1, subject: '会員登録と商品詳細を進めて', owner: 'b4', spec: null, created: -1, start: -1, end: null },
  { list: '4f', id: 'turn-1', source: 'turn', turn: 1, subject: 'jui build の iOS 出力を直して', owner: '4f', spec: null, created: -1, start: -1, end: 24 },
  { list: '4f', id: 'turn-2', source: 'turn', turn: 2, subject: 'jui viz の雛形を作って', owner: '4f', spec: null, created: 40, start: 40, end: null, waitFrom: 42, waitTo: 44 },
  { list: 'c9', id: 'turn-1', source: 'turn', turn: 1, subject: 'spec の構造ページを生成して', owner: 'c9', spec: null, created: -1, start: -1, end: 60 },
);
const TASK_BY_KEY = Object.fromEntries(TASKS.map((x) => [`${x.list}#${x.id}`, x]));
const EVENTS = [
  [0.2, 'a5', 'Read', 'docs/screens/json/home.spec.json'],
  [0.4, 'f2', 'Edit', 'docs/screens/layouts/product-detail.json'],
  [0.6, 'c9', 'Read', 'docs/screens/json/spec-anatomy.spec.json'],
  [1.4, '7c', 'Edit', 'src/reporter/progress.ts'],
  [1.0, '4f', 'Bash', 'jui build --ios-only'],
  [2.0, 'b4', 'TaskCreated', '#5 ProductDetail → Cart の遷移をつなぐ'],
  [5.0, 'a3', 'Write', 'docs/screens/json/login.spec.json'],
  [6.0, 'e6', 'PermissionRequest', 'Write docs/screens/json/signup.spec.json', 'p1'],
  [6.0, 'a5', 'Edit', 'docs/screens/layouts/home.json'],
  [8.0, 'e6', 'Write', 'docs/screens/json/signup.spec.json'],
  [9.0, 'a3', 'spec 更新', 'login.spec.json › structure'],
  [10.0, 'a2', 'MCP', 'jui-tools test_validate cart.test.json'],
  [12.0, 'a0', 'TaskCreated', '#7 Home → Cart の遷移をつなぐ'],
  [12.2, 'e6', 'spec 更新', 'signup.spec.json › structure'],
  [12.4, 'a0', 'TaskCreated', '#8 jui verify で spec とのズレを確認'],
  [14.0, 'a2', 'PermissionRequest', "Bash xcodebuild test -destination 'iPhone 16'", 'p2'],
  [16.0, 'c9', 'PermissionRequest', 'Bash jsonui-doc generate html', 'p3'],
  [18.0, 'a2', 'Bash', "xcodebuild test -destination 'iPhone 16'"],
  [20.0, 'e1', 'Write', 'docs/screens/json/attribute-reference.spec.json'],
  [22.0, '4f', 'Stop', 'ビルド完了'],
  [23.0, 'a2', 'case ✓', '初期表示（商品 3 点）'],
  [25.0, 'a3', 'spec 更新', 'login.spec.json › stateManagement'],
  [26.0, 'f2', 'PermissionRequest', 'Bash jui build', 'p4'],
  [28.0, 'a2', 'case ✓', '数量を 0 にすると行が消える'],
  [30.0, 'f2', 'Bash', 'jui build'],
  [30.2, 'f2', 'TaskCompleted', '#2 ProductDetail のレイアウトを実装'],
  [30.4, 'e6', 'spec 更新', 'signup.spec.json › stateManagement'],
  [30.6, '7c', 'PermissionRequest', 'Bash npm test -- --progress', 'p7'],
  [26.2, 'e1', 'spec 更新', 'attribute-reference.spec.json › structure'],
  [32.0, 'a2', 'case ✓', '空のカートで購入ボタンが無効'],
  [33.0, 'a3', 'spec 更新', 'login.spec.json › dataFlow'],
  [36.0, 'f2', 'Edit', 'ProductDetailViewModel.swift'],
  [37.0, 'a2', 'case ✓', 'クーポン WELCOME10 を適用'],
  [38.0, 'c9', 'PostToolUse', 'jsonui-doc generate html（許可済み）'],
  [40.0, 'a5', 'Bash', 'jui build'],
  [40.2, 'e6', 'spec 更新', 'signup.spec.json › dataFlow'],
  [40.4, 'e1', 'spec 更新', 'attribute-reference.spec.json › stateManagement'],
  [42.0, '4f', 'PermissionRequest', 'Bash pip install aiohttp watchdog', 'p6'],
  [40.5, 'a5', 'TaskCompleted', '#3 Home のレイアウトを実装'],
  [41.0, 'a2', 'case ✗', '期限切れクーポンでエラー表示（1 回目）'],
  [41.2, 'a2', 'retry', '期限切れクーポンでエラー表示を再実行'],
  [43.0, 'a3', 'spec 更新', 'login.spec.json › userActions'],
  [45.0, 'a2', 'case ✓', '期限切れクーポンでエラー表示（2 回目で通過）'],
  [45.2, 'a5', 'PermissionRequest', 'Edit HomeViewModel.swift', 'p5'],
  [48.0, 'a5', 'Edit', 'HomeViewModel.swift'],
  [50.0, '4f', 'Edit', 'jui_cli/commands/viz_cmd.py'],
  [50.2, 'a2', 'case ✓', '在庫切れ商品の警告'],
  [50.4, 'e6', 'spec 更新', 'signup.spec.json › userActions'],
  [48.2, 'e1', 'spec 更新', 'attribute-reference.spec.json › dataFlow'],
  [58.4, 'e1', 'spec 更新', 'attribute-reference.spec.json › userActions'],
  [60.6, '7c', 'Bash', 'npm test'],
  [64.4, 'e1', 'spec 更新', 'attribute-reference.spec.json › transitions'],
  [70.6, 'e1', 'spec 更新', 'attribute-reference.spec.json › branchContracts'],
  [78.0, 'e1', 'Stop', '属性リファレンスの spec を書き終えた'],
  [78.4, 'e1', 'TaskCompleted', '#1 属性リファレンスの spec を書く'],
  [52.0, 'c9', 'Stop', 'HTML を生成した'],
  [55.0, 'a3', 'spec 更新', 'login.spec.json › branchContracts'],
  [55.2, 'a2', 'case ✓', '未ログインで購入 → ログイン画面へ'],
  [58.2, 'e6', 'spec 更新', 'signup.spec.json › transitions'],
  [60.0, 'a2', 'case ✓', '購入確定で注文完了へ'],
  [60.2, 'a2', 'TaskCompleted', '#5 Cart のテスト 8/8 通過（1 件は再実行）'],
  [62.0, 'a3', 'SubagentStop', 'Login の spec を書き終えた'],
  [62.2, 'a3', 'TaskCompleted', '#2 Login 画面の spec を書く'],
  [64.2, 'e6', 'spec 更新', 'signup.spec.json › branchContracts'],
  [70.0, 'a5', 'MCP', 'jui-tools jui_verify home.spec.json'],
  [70.2, 'e6', 'SubagentStop', 'Signup の spec を書き終えた'],
  [70.4, 'e6', 'TaskCompleted', '#1 Signup 画面の spec を書く'],
  [72.0, 'a5', 'PostToolUse', 'jui_verify: ズレ 0'],
  [74.0, 'a5', 'TaskCompleted', '#8 jui verify で spec とのズレを確認'],
  [74.2, 'f2', 'MCP', 'jui-tools jui_verify product-detail.spec.json'],
  [76.0, 'a5', 'TaskCompleted', '#4 Home の ViewModel を実装'],
  [76.2, 'a5', 'SubagentStop', 'Home の実装が終わった'],
  [76.4, 'f2', 'PostToolUse', 'jui_verify: ズレ 0'],
  [78.0, 'f2', 'TaskCompleted', '#3 ProductDetail の ViewModel を実装'],
  [78.2, 'f2', 'SubagentStop', 'ProductDetail の実装が終わった'],
];

EVENTS.sort((a, b) => a[0] - b[0]);

/* ---------- model: what every panel shows at script time t ---------- */
function planAt(plan, t) { let cur = plan[0]; for (const p of plan) if (t >= p[0]) cur = p; return { state: cur[1], act: cur[2] }; }
const WALK_SEGS = (() => {
  const segs = [];
  let t = 0;
  WALK.points.forEach((a, i) => {
    const b = WALK.points[(i + 1) % WALK.points.length];
    const dur = Math.hypot(b[0] - a[0], b[1] - a[1]) / WALK.speed;
    segs.push({ a, b, t0: t, t1: t + dur });
    t += dur + WALK.pause;
  });
  return { segs, cycle: t };
})();
function walkAt(simT) {
  const tau = ((simT % WALK_SEGS.cycle) + WALK_SEGS.cycle) % WALK_SEGS.cycle;
  for (const s of WALK_SEGS.segs) {
    const ry = Math.atan2(s.b[0] - s.a[0], s.b[1] - s.a[1]);
    if (tau >= s.t0 && tau < s.t1) { const k = (tau - s.t0) / (s.t1 - s.t0); return { x: s.a[0] + (s.b[0] - s.a[0]) * k, z: s.a[1] + (s.b[1] - s.a[1]) * k, ry, moving: true }; }
    if (tau >= s.t1 && tau < s.t1 + WALK.pause) return { x: s.b[0], z: s.b[1], ry, moving: false };
  }
  return { x: WALK.points[0][0], z: WALK.points[0][1], ry: 0, moving: false };
}

function computeTests(t) {
  const rows = CASES.map((c) => {
    if (t < c.s) return { ...c, status: 'pending' };
    if (t < c.e) {
      const retry = c.failAt && t >= c.failAt;
      const k = retry ? frac(t, c.failAt, c.e) : frac(t, c.s, c.failAt || c.e);
      return { ...c, status: 'running', attempt: retry ? 2 : 1, step: c.steps[Math.min(c.steps.length - 1, Math.floor(k * c.steps.length))] };
    }
    return { ...c, status: c.failAt ? 'flaky' : 'passed' };
  });
  const passed = rows.filter((r) => r.status === 'passed' || r.status === 'flaky').length;
  const runningIdx = rows.findIndex((r) => r.status === 'running');
  const retrying = runningIdx >= 0 && rows[runningIdx].attempt === 2;
  let statusText;
  if (t < 10) statusText = '待機中（前回は 5/8 通過）';
  else if (t < 18) statusText = 'test_validate でテスト JSON を検証中';
  else if (t < 60) statusText = `実行中 ${passed}/8 通過 · ケース ${runningIdx + 1} を実行中`;
  else statusText = '完了 8/8 通過（1 件は再実行で通過）';
  return { rows, passed, runningIdx, retrying, active: t >= 18 && t < 60, statusText, file: 'tests/screens/cart.test.json', device: 'iPhone 16 シミュレータ' };
}

const BLANK = [0, 0, 0, 0, 0, 0, 0];
const FULL = [1, 1, 1, 1, 1, 1, 1];
/* Sections are written in order, so a share of the whole spec fills them one after another. */
const spread = (share) => SECTIONS.map((_, k) => clamp01(share * SECTIONS.length - k));
function spreadImpl(totals, share) {
  let left = Math.round(sumImpl(totals) * share);
  return totals.map((n, k) => { if (k < 1 || k > 5) return 0; const v = Math.min(n, left); left -= v; return v; });
}
function stillState(s) {
  const [phase, share = 0] = STILL[s.id] || ['todo'];
  const T = s.totals;
  const base = { written: FULL, implN: BLANK, implPhase: false, writingIdx: -1, implIdx: -1, testIdx: -1, by: null, relatedNow: -1 };
  switch (phase) {
    case 'todo': return { ...base, written: BLANK, status: { kind: 'idle', text: '未着手' }, note: 'spec ファイルはまだない' };
    case 'writing': return { ...base, written: spread(share), status: { kind: 'paused', text: `記述 ${pct(share)}%・中断中` }, note: '書きかけのまま止まっている（担当なし）' };
    case 'written': return { ...base, status: { kind: 'written', text: '記述完了・実装待ち' }, note: '実装はまだ始まっていない' };
    case 'impl': return { ...base, implN: spreadImpl(T, share), implPhase: true, status: { kind: 'paused', text: `実装 ${pct(share)}%・停止中` }, note: '実装の途中で止まっている（担当なし）' };
    case 'impl-done': return { ...base, implN: T.map((n, k) => (k === 6 ? 0 : n)), implPhase: true, status: { kind: 'impl-done', text: '実装完了・テスト待ち' }, note: 'jui verify: ズレ 0 · テストはまだ' };
    default: return { ...base, implN: [...T], implPhase: true, status: { kind: 'done', text: '実装・テスト完了' }, note: `jui verify: ズレ 0 · branchContracts ${T[6]}/${T[6]}` };
  }
}
/* A define robot writing a spec section by section, watched through file changes. */
function writingSpec(t, W, who, chars) {
  const t0 = W[0][0], t1 = W[W.length - 1][1];
  const idx = W.findIndex(([a, b]) => t >= a && t < b);
  const writing = t >= t0 && t < t1;
  return {
    written: W.map(([a, b]) => frac(t, a, b)), implN: BLANK, implPhase: false, writingIdx: writing ? idx : -1, implIdx: -1, testIdx: -1, by: writing ? who : null, relatedNow: -1,
    status: t < t0 ? { kind: 'idle', text: '未着手' } : writing ? { kind: 'write', text: `書き込み中 ${pct(frac(t, t0, t1))}%` } : { kind: 'written', text: '記述完了・実装待ち' },
    note: writing ? `${Math.round(chars * frac(t, t0, t1)).toLocaleString('ja-JP')} 文字 · ファイル監視で ${SECTIONS[idx]} の書き込みを検知` : t < t0 ? 'spec ファイルはまだない' : `${chars.toLocaleString('ja-JP')} 文字 · 全セクション記述済み`,
  };
}
const LOGIN_W = [[5, 9], [9, 25], [25, 33], [33, 43], [43, 49], [49, 55], [55, 62]];
const SIGNUP_W = [[8, 12], [12, 30], [30, 40], [40, 50], [50, 58], [58, 64], [64, 70]];
const ATTRS_W = [[20, 26], [26, 40], [40, 48], [48, 58], [58, 64], [64, 70], [70, 78]];
function computeSpecs(t, tests) {
  const out = SPECS.map((s) => ({ ...s, ...stillState(s) }));
  const put = (id, o) => { const i = SPEC_INDEX[id]; out[i] = { ...out[i], ...o }; };

  // a3 writes Login, then runs doc_validate_spec on it; e6 (session b4) writes Signup.
  const login = writingSpec(t, LOGIN_W, 'a3', 5200);
  if (t >= 70 && t < 76) Object.assign(login, { by: 'a3', status: { kind: 'verify', text: 'doc_validate_spec 実行中' } });
  put('login', login);
  put('signup', writingSpec(t, SIGNUP_W, 'e6', 5600));
  put('attrs', writingSpec(t, ATTRS_W, 'e1', 4800));

  // a5 implements Home: Layout first, then the ViewModel, then jui verify.
  const H = SPECS[SPEC_INDEX.home].totals;
  const hd = [0, t < 6 ? 3 : 3 + Math.floor(9 * frac(t, 6, 40)), Math.floor(5 * frac(t, 48, 66)), Math.floor(6 * frac(t, 48, 70)), Math.floor(4 * frac(t, 56, 72)), Math.floor(2 * frac(t, 60, 72)), 0];
  let hIdx = -1;
  if (t >= 6 && t < 48) hIdx = 1; else if (t >= 48 && t < 58) hIdx = 2; else if (t >= 58 && t < 66) hIdx = 3; else if (t >= 66 && t < 70) hIdx = 4;
  put('home', {
    written: FULL, implN: hd, implPhase: true, writingIdx: -1, implIdx: hIdx, testIdx: -1,
    status: t < 6 ? { kind: 'impl', text: 'spec を読み込み中' } : t < 70 ? { kind: 'impl', text: `実装中 ${pct(sumImpl(hd) / sumImpl(H))}%` } : t < 76 ? { kind: 'verify', text: 'jui verify 実行中' } : { kind: 'impl-done', text: '実装完了・テスト待ち' },
    by: t < 76 ? 'a5' : null, relatedNow: hIdx === 1 ? 0 : hIdx >= 2 ? 1 : -1,
    note: `jui verify: ${t < 70 ? '未実行（構造は Layout の部品 id で照合中）' : t < 72 ? '確認中…' : 'ズレ 0'}`,
  });

  // f2 (session b4) implements ProductDetail the same way.
  const D = SPECS[SPEC_INDEX.detail].totals;
  const dd = [0, Math.min(D[1], 4 + Math.floor((D[1] - 4) * frac(t, 0, 30))), Math.floor(D[2] * frac(t, 36, 56)), Math.floor(D[3] * frac(t, 36, 70)), Math.floor(D[4] * frac(t, 48, 72)), Math.floor(D[5] * frac(t, 60, 74)), 0];
  let dIdx = -1;
  if (t < 30) dIdx = 1; else if (t >= 36 && t < 50) dIdx = 2; else if (t >= 50 && t < 62) dIdx = 3; else if (t >= 62 && t < 70) dIdx = 4; else if (t >= 70 && t < 74) dIdx = 5;
  const dPct = `実装中 ${pct(sumImpl(dd) / sumImpl(D))}%`;
  put('detail', {
    written: FULL, implN: dd, implPhase: true, writingIdx: -1, implIdx: dIdx, testIdx: -1,
    status: t < 30 ? { kind: 'impl', text: dPct } : t < 36 ? { kind: 'impl', text: 'jui build 実行中' } : t < 74 ? { kind: 'impl', text: dPct } : t < 78 ? { kind: 'verify', text: 'jui verify 実行中' } : { kind: 'impl-done', text: '実装完了・テスト待ち' },
    by: t < 78 ? 'f2' : null, relatedNow: dIdx === 1 || (t >= 30 && t < 36) ? 0 : dIdx >= 2 ? 1 : -1,
    note: `jui verify: ${t < 74 ? '未実行' : t < 76 ? '確認中…' : 'ズレ 0'}`,
  });

  // a2 runs the Cart tests on the simulator; each passing case covers one branchContract.
  const C = SPECS[SPEC_INDEX.cart].totals;
  const cov = t < 18 ? 5 : tests.passed;
  put('cart', {
    written: FULL, implN: [...C.slice(0, 6), cov], implPhase: true, writingIdx: -1, implIdx: -1, testIdx: tests.active ? 6 : -1,
    status: t < 10 ? { kind: 'impl-done', text: '実装完了・テスト待ち' } : t < 18 ? { kind: 'test', text: 'テスト JSON を検証中' } : t < 60 ? { kind: 'test', text: `テスト中 ${tests.passed}/8` } : { kind: 'done', text: '実装・テスト完了' },
    by: t >= 10 && t < 60 ? 'a2' : null, relatedNow: t >= 10 && t < 60 ? 2 : -1,
    note: `branchContracts: ${cov}/8 をテストで確認${t < 18 ? '（前回の実行）' : ''}`,
  });
  for (const s of out) s.bucket = s.by ? 'live' : s.status.kind === 'idle' ? 'todo' : s.status.kind === 'done' ? 'done' : 'partial';
  return out;
}


/* Permission prompts in the demo: who asks for what, for which task, and when the script answers them in the
   terminal if nobody answers in the view first. `rule` is what "always allow" would add. */
const PERMS = [
  { id: 'p1', who: 'e6', task: 'b4#1', tool: 'Write', input: { file_path: 'docs/screens/json/signup.spec.json' }, rule: 'Write(docs/screens/json/**)', at: 6, end: 8 },
  { id: 'p2', who: 'a2', task: 'a0#5', tool: 'Bash', input: { command: "xcodebuild test -scheme ShopApp -destination 'platform=iOS Simulator,name=iPhone 16'" }, rule: 'Bash(xcodebuild test:*)', at: 14, end: 18 },
  { id: 'p3', who: 'c9', task: 'c9#1', tool: 'Bash', input: { command: 'jsonui-doc generate html --spec docs/screens/json/spec-anatomy.spec.json' }, rule: 'Bash(jsonui-doc generate:*)', at: 16, end: 38 },
  { id: 'p6', who: '4f', task: null, tool: 'Bash', input: { command: 'pip install aiohttp watchdog' }, rule: 'Bash(pip install:*)', at: 42, end: 44 },
  { id: 'p7', who: '7c', task: '7c#1', tool: 'Bash', input: { command: 'npm test -- --progress' }, rule: 'Bash(npm test:*)', at: 30.6, end: 36 },
  { id: 'p4', who: 'f2', task: 'b4#2', tool: 'Bash', input: { command: 'jui build' }, rule: 'Bash(jui build:*)', at: 26, end: 30 },
  { id: 'p5', who: 'a5', task: 'a0#4', tool: 'Edit', input: { file_path: 'ios/ShopApp/ViewModels/HomeViewModel.swift' }, rule: 'Edit(ios/ShopApp/**)', at: 45.2, end: 48 },
];
const PERM_BY_ID = Object.fromEntries(PERMS.map((p) => [p.id, p]));
const permDecisions = new Map();   // `${loop}:${id}` → { behavior: 'allow' | 'always' | 'deny', at, reason }
const alwaysRules = new Map();     // rule → sim time it was added in the view
/* What Claude Code sends with a permission prompt (PermissionRequest hook input) and what the view answers. */
const ruleParts = (rule) => { const m = rule.match(/^(\w+)\((.*)\)$/); return m ? { toolName: m[1], ruleContent: m[2] } : { toolName: rule }; };
function permRequestPayload(p) {
  const sess = SESSION_OF[p.who];
  const o = { hook_event_name: 'PermissionRequest', session_id: SESSION_UUID[sess], cwd: CWD[sess], permission_mode: 'default' };
  if (AGENT_ID[p.who]) { o.agent_id = AGENT_ID[p.who]; o.agent_type = DEF[p.who].agent; }
  o.tool_name = p.tool;
  o.tool_input = p.input.command ? { command: p.input.command } : { file_path: `${CWD[sess]}/${p.input.file_path}` };
  o.permission_suggestions = [{ type: 'addRules', rules: [ruleParts(p.rule)], behavior: 'allow', destination: 'localSettings' }];
  return o;
}
function permResponse(p, behavior, reason) {
  const decision = behavior === 'deny' ? { behavior: 'deny', message: reason || 'エージェントビューで拒否された' } : { behavior: 'allow' };
  if (behavior === 'always') decision.updatedPermissions = [{ type: 'addRules', rules: [ruleParts(p.rule)], behavior: 'allow', destination: 'localSettings' }];
  return { hookSpecificOutput: { hookEventName: 'PermissionRequest', decision } };
}
function computePerms(t, loop) {
  return PERMS.filter((p) => t >= p.at).map((p) => {
    const d = permDecisions.get(`${loop}:${p.id}`) || null;
    const status = d ? d.behavior : ruleCovers(p, loop * LOOP + p.at) ? 'rule' : t < p.end ? 'pending' : 'terminal';
    return { ...p, status, decided: d, since: t - p.at };
  });
}
function computeTasks(t) {
  const statusOf = (task) => {
    if (task.created > t) return null;
    if (task.end !== null && task.end !== undefined && t >= task.end) return 'completed';
    if (task.start !== null && task.start !== undefined && t >= task.start) return 'in_progress';
    return 'pending';
  };
  const byKey = Object.fromEntries(TASKS.map((x) => [`${x.list}#${x.id}`, x]));
  return TASKS.map((task) => {
    const status = statusOf(task);
    const dep = task.blockedBy ? byKey[`${task.list}#${task.blockedBy}`] : null;
    const blocked = status === 'pending' && !!dep && statusOf(dep) !== 'completed';
    const waiting = status === 'in_progress' && task.waitFrom !== undefined && t >= task.waitFrom && t < task.waitTo;
    const col = status === 'completed' ? 'done' : status === 'in_progress' ? (waiting ? 'wait' : 'doing') : blocked ? 'wait' : 'todo';
    return { ...task, key: `${task.list}#${task.id}`, status, blocked, dep, col, waiting, fresh: task.created >= 0 && t - task.created < 1.5 };
  }).filter((task) => task.status);
}

function computeModel(t, loop = 0) {
  const tests = computeTests(t), perms = computePerms(t, loop), tasks = computeTasks(t);
  for (const x of tasks) x.perm = perms.find((p) => p.task === x.key && p.status === 'pending') || null;
  return { t, loop, tests, specs: computeSpecs(t, tests), tasks, perms, pending: perms.filter((p) => p.status === 'pending') };
}

/* ---------- the demo's show (10-18): everything the live view can do, once a loop ----------
   The demo clock runs 5:00 → 23:00 over the 84 s (the sky; b4's session began at 9:00, so it tires at 17:00). The
   beats stay out of 26–33 s, where the e2e suites freeze the script to compare it with the prototype. The camera
   beats only play while nobody has touched the 3D view for a while (demoDirector, 40-scene.js). */
const DEMO_DAY = { from: 5, to: 23 };
const demoHour = (t) => DEMO_DAY.from + ((DEMO_DAY.to - DEMO_DAY.from) * ((((t % LOOP) + LOOP) % LOOP))) / LOOP;
const demoDayMs = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime(); };
const demoClockMs = (t) => demoDayMs() + Math.round(demoHour(t) * 3600000);
const DEMO_BEATS = {
  towerOut: 36, look2F: 40, look1F: 44, towerIn: 47,   // by day: out to the building, up to 2F, back to 1F, down
  nightOut: 70, nightIn: 78,                            // at night: the rooms working late lit, the sign aglow
  thinking: [34, 50, 'd8'],                             // a quiet busy session (d8's plan)
  heavy: [38, 58, '7c'],                                // heavy work: fast typing and sweat
  tired: { session: 'b4', since: 9 },                   // the session began at 9:00 of the demo clock
  snacks: [[34, '4f', 'coffee'], [42, 'e1', 'coffee'], [64, 'c9', 'meal']],
};
// The building's data, as the live source keeps it (40-scene.js reads it): 1F the demo's three rooms and three
// other teams', 2F four more. The other teams work by the demo clock: [from hour, to hour, rank 0 waiting | 1 working].
const LIVE = { floors: [['shop', 'cli', 'doc', 'x1', 'x2', 'x3'], ['y1', 'y2', 'y3', 'y4']], floor: 0, rank: {}, leaving: {} };
const PERMS_LIVE = [];
Object.assign(TOWER_NAMES, { x1: 'design-system/', x2: 'payments/', x3: 'infra/', y1: 'ec-site/', y2: 'admin-web/', y3: 'blog-cms/', y4: 'mobile-api/' });
const DEMO_OTHERS = { x1: [[8, 18, 1]], x2: [[9, 12, 1], [12, 14, 0], [14, 19, 1]], x3: [[10, 16, 1]], y1: [[9, 19, 1]], y2: [[8, 24, 1]], y3: [], y4: [[11, 17, 1]] };
function liveGoToFloor() { return false; }   // one office: the other floors are only in the building view
function liveFloorOf() { return 0; }
function demoBuilding(t) {
  const h = demoHour(t), rank = {};
  for (const r of ROOMS) rank[r.id] = 3;
  for (const d of ROBOT_DEFS) {
    const room = projectOfRobot(d.id), st = (robotState[d.id] || {}).state;
    if (room) rank[room] = Math.min(rank[room], st === 'waiting' ? 0 : st && st !== 'idle' && st !== 'done' ? 1 : 2);
  }
  for (const [id, spans] of Object.entries(DEMO_OTHERS)) { const span = spans.find(([a, b]) => h >= a && h < b); rank[id] = span ? span[2] : 2; }
  LIVE.rank = rank;
}
const demoTired = (id) => id === DEMO_BEATS.tired.session && isTired(demoDayMs() + DEMO_BEATS.tired.since * 3600000, vizNow());
const demoHeavy = (id, t) => id === DEMO_BEATS.heavy[2] && t >= DEMO_BEATS.heavy[0] && t < DEMO_BEATS.heavy[1];
function robotCondition(id) {
  const t = latestModel ? latestModel.t : 0;
  return { tired: demoTired(id), hours: (vizNow() - demoDayMs()) / 3600000 - DEMO_BEATS.tired.since,
    heavy: demoHeavy(id, t) ? { reasons: ['tokens'], tokensPerMin: 3200 } : null };
}

/* ---------- the source's face to the rest of the view (plan 07 §2) ---------- */
// The demo answers a permission prompt on the spot: it records the answer for this loop of the script (and the
// rule for "always"), logs it and says what a real answer would do. The live source sends perm.decide instead.
const SOURCE = {
  mode: 'demo', layoutRev: 0, connected: true,
  decide(id, behavior, { perm: p, reason = '' }) {
    const loop = latestModel.loop;
    permDecisions.set(`${loop}:${id}`, { behavior, at: simT, reason });
    for (const k of permDecisions.keys()) if (Number(k.split(':')[0]) < loop) permDecisions.delete(k);
    if (behavior === 'always') alwaysRules.set(p.rule, simT);
    const item = { abs: simT, who: p.who, kind: behavior === 'deny' ? '拒否した' : '許可した', what: `${p.tool} ${permSummary(p)}${behavior === 'always' ? `（今後も許可: ${p.rule}）` : ''}${reason ? `（理由: ${reason}）` : ''}`, seq: ++logSeq, perm: id, decision: behavior, reason };
    tickerItems.unshift(item); logItems.unshift(item);
    showToast(`${p.who} の ${p.tool} を${behavior === 'deny' ? '拒否' : behavior === 'always' ? '許可し、ルールを追加' : '許可'}した（デモ。実際は Claude Code へ答えを返す）`);
  },
};

/* ---------- robot states (kept even without WebGL so the panels still run) ---------- */
const robotState = Object.fromEntries(ROBOT_DEFS.map((d) => [d.id, { state: 'idle', act: '' }]));
function updateRobotStates(simT, t, perms) {
  for (const d of ROBOT_DEFS) {
    if (d.walk) {
      const w = walkAt(simT);
      const started = t >= TASK_BY_KEY['a0#7'].start;
      robotState[d.id] = { state: w.moving ? 'carry' : 'idle', act: w.moving ? (started ? '書類を運搬中（#7 Home → Cart の遷移）' : '下調べの資料を運搬中（#7 は #3 の完了待ち）') : '書類を渡す', walk: w };
      continue;
    }
    let st = planAt(d.plan, t);
    // While a permission prompt is open the robot waits; an answer from the view lets it go on before the script would.
    const p = perms.find((x) => x.who === d.id && t < x.end && x.status !== 'terminal');
    if (p && p.status === 'pending') st = { state: 'waiting', act: `許可待ち: ${p.tool} ${permSummary(p)}` };
    else if (p && p.status === 'deny') st = { state: 'reading', act: '拒否されたので別の手を考え中' };
    else if (p) { const next = planAt(d.plan, p.end); st = { state: next.state, act: `${next.act}（${p.status === 'rule' ? 'ルールで自動許可' : 'ビューで許可'}）` }; }
    robotState[d.id] = st;
  }
}
