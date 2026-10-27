
/* =====================================================================
   JsonUI Agent View: demo script, 3D office and live side panel
   ===================================================================== */

/* ---------- demo script: one 84-second loop of a JsonUI project ---------- */
const LOOP = 84;
const START_AT = 24;
const BASE_CLOCK = 14 * 3600 + 20 * 60;

const ROOMS = [
  { id: 'shop', name: 'shop-app/', path: '~/work/shop-app', x0: -9.6, x1: 2.6, z0: -5.0, z1: 4.2, floor: '--floor-a', back: 3.9, left: 3.9, infraDocs: { files: 2, dir: 'docs/infra' } },
  { id: 'cli', name: 'shop-tools/', path: '~/work/shop-tools', x0: 3.1, x1: 10.2, z0: -5.0, z1: -0.25, floor: '--floor-b', back: 3.9, left: 0.55 },
  { id: 'doc', name: 'docs-site/', path: '~/work/docs-site', x0: 3.1, x1: 10.2, z0: 0.25, z1: 4.2, floor: '--floor-c', back: 0.55, left: 0.55 },
];
/* One room per project folder; a project can hold any number of sessions. */
const PROJECT = Object.fromEntries(ROOMS.map((r) => [r.id, r]));
const SESSIONS = [
  { id: 'a0', project: 'shop', robots: ['a0', 'a3', 'a5', 'a2', 'a7'] },
  { id: 'b4', cli: 'codex', project: 'shop', robots: ['b4', 'e6', 'f2'] },
  { id: 'd8', project: 'shop', robots: ['d8'] },
  { id: '4f', project: 'cli', robots: ['4f'] },
  { id: '7c', cli: 'codex', project: 'cli', robots: ['7c'] },
  { id: 'c9', project: 'doc', robots: ['c9'] },
  { id: 'e1', project: 'doc', robots: ['e1'] },
].map((s) => ({ ...s, room: PROJECT[s.project].name }));
// cli: which CLI runs the session (the demo has two Codex sessions, b4 and 7c; the rest are Claude Code's)
const ROBOT_DEFS = [
  { id: 'a0', role: 'main', agent: tl('demo.robot.session.a07c'), pos: [0.7, -2.5], ry: 0.3, furnished: true,
    plan: [[0, 'reading', 'Read docs/screens/json/cart.spec.json'], [12, 'typing', tl('demo.robot.taskcreate.7.8')], [20, 'idle', tl('demo.robot.waiting.subagent.reports')], [62, 'reading', tl('demo.robot.reviewing.a3.s.report')], [70, 'typing', tl('demo.robot.checking.what.s.left.tasklist')], [76, 'idle', tl('demo.robot.waiting.subagent.reports')]] },
  { id: 'a3', role: 'define', agent: 'jsonui-define', pos: [-6.3, -3.1], ry: 0.55, furnished: true,
    plan: [[0, 'reading', tl('demo.robot.read.home.spec.json.reference')], [5, 'typing', 'Write docs/screens/json/login.spec.json'], [62, 'done', tl('demo.robot.finished.login.spec')], [66, 'idle', tl('demo.robot.idle')], [70, 'reading', 'doc_validate_spec login'], [76, 'idle', tl('demo.robot.idle')]] },
  { id: 'a5', role: 'implement', agent: 'jsonui-implement', pos: [-2.7, -2.7], ry: 0.5, furnished: true,
    plan: [[0, 'reading', 'Read docs/screens/json/home.spec.json'], [6, 'typing', 'Edit docs/screens/layouts/home.json'], [40, 'command', 'Bash jui build'], [48, 'typing', 'Edit HomeViewModel.swift'], [70, 'command', 'jui_verify home.spec.json'], [76, 'done', tl('demo.robot.finished.implementing.home')], [80, 'idle', tl('demo.robot.idle')]] },
  { id: 'a2', role: 'test', agent: 'jsonui-test', pos: [-7.3, 1.2], ry: 0.75,
    plan: [[0, 'idle', tl('demo.robot.idle')], [10, 'command', 'test_validate cart.test.json'], [18, 'phone', tl('demo.robot.xcodebuild.test.iphone.16')], [60, 'done', tl('demo.robot.cart.tests.8.8.passed')], [66, 'idle', tl('demo.robot.idle')]] },
  { id: 'a7', role: 'navigation', agent: 'jsonui-navigation-ios', walk: true },
  { id: 'b4', cli: 'codex', role: 'main', agent: tl('demo.robot.session.b47e'), pos: [-0.4, 3.5], ry: 0.15, furnished: true,
    plan: [[0, 'typing', 'TaskCreate #5'], [6, 'idle', tl('demo.robot.waiting.subagent.reports')], [70, 'reading', tl('demo.robot.reviewing.e6.s.report')], [74, 'idle', tl('demo.robot.waiting.subagent.reports')]] },
  { id: 'e6', cli: 'codex', role: 'define', agent: 'jsonui-define', pos: [-2.9, 3.4], ry: 0.25, furnished: true,
    plan: [[0, 'reading', tl('demo.robot.read.login.spec.json.reference')], [8, 'typing', 'Write docs/screens/json/signup.spec.json'], [70, 'done', tl('demo.robot.finished.signup.spec')], [74, 'idle', tl('demo.robot.idle')]] },
  { id: 'f2', cli: 'codex', role: 'implement', agent: 'jsonui-implement', pos: [-5.3, 3.3], ry: 0.4, furnished: true,
    plan: [[0, 'typing', 'Edit docs/screens/layouts/product-detail.json'], [30, 'command', 'Bash jui build'], [36, 'typing', 'Edit ProductDetailViewModel.swift'], [74, 'command', 'jui_verify product-detail.spec.json'], [78, 'done', tl('demo.robot.finished.implementing.productdetail')], [82, 'idle', tl('demo.robot.idle')]] },
  { id: 'd8', role: 'main', agent: tl('demo.robot.session.d8a5'), pos: [-8.5, -3.5], ry: 0.6, furnished: true,
    plan: [[0, 'idle', tl('demo.robot.idle.waiting.next.prompt')], [34, 'thinking', tl('demo.robot.thinking')], [50, 'idle', tl('demo.robot.idle.waiting.next.prompt')]] },
  { id: '4f', role: 'main', agent: tl('demo.robot.session.4f2b'), pos: [6.0, -2.9], ry: 0.05, furnished: true,
    plan: [[0, 'command', 'Bash jui build --ios-only'], [22, 'done', tl('demo.robot.build.complete')], [26, 'idle', tl('demo.robot.idle')], [38, 'reading', 'Read jui_cli/commands/hotload_cmd.py'], [44, 'command', 'Bash pip install aiohttp watchdog'], [47, 'typing', 'Edit jui_cli/commands/viz_cmd.py'], [78, 'reading', tl('demo.robot.reviewing.diff')]] },
  { id: '7c', cli: 'codex', role: 'main', agent: tl('demo.robot.session.7c3f'), pos: [8.9, -2.6], ry: -0.15, furnished: true,
    plan: [[0, 'typing', 'Edit src/reporter/progress.ts'], [30, 'command', 'Bash npm test -- --progress'], [36, 'typing', 'Edit src/cli/run.ts'], [60, 'command', 'Bash npm test'], [66, 'reading', tl('demo.robot.checking.test.results')]] },
  { id: 'c9', role: 'main', agent: tl('demo.robot.session.c91e'), pos: [6.4, 2.0], ry: 0.1, furnished: true,
    plan: [[0, 'reading', 'Read docs/screens/json/spec-anatomy.spec.json'], [38, 'command', 'Bash jsonui-doc generate html'], [52, 'done', tl('demo.robot.generated.html')], [56, 'idle', tl('demo.robot.idle')]] },
  { id: 'e1', role: 'main', agent: tl('demo.robot.session.e1d4'), pos: [8.7, 2.6], ry: -0.1, furnished: true,
    plan: [[0, 'reading', tl('demo.robot.read.component.detail.spec.json')], [20, 'typing', 'Write docs/screens/json/attribute-reference.spec.json'], [78, 'done', tl('demo.robot.finished.attribute.reference.spec')], [82, 'idle', tl('demo.robot.idle')]] },
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
  ['onboarding', 'Onboarding', tl('demo.screen.onboarding'), 'onboarding'],
  ['login', 'Login', tl('demo.screen.login'), 'login'],
  ['signup', 'Signup', tl('demo.screen.signup'), 'signup'],
  ['reset', 'PasswordReset', tl('demo.screen.reset'), 'password-reset'],
  ['home', 'Home', tl('demo.screen.home'), 'home'],
  ['search', 'Search', tl('demo.screen.search'), 'search'],
  ['filter', 'FilterSheet', tl('demo.screen.filter'), 'filter-sheet'],
  ['list', 'ProductList', tl('demo.screen.list'), 'product-list'],
  ['detail', 'ProductDetail', tl('demo.screen.detail'), 'product-detail'],
  ['reviews', 'Reviews', tl('demo.screen.reviews'), 'reviews'],
  ['favorites', 'Favorites', tl('demo.screen.favorites'), 'favorites'],
  ['cart', 'Cart', tl('demo.screen.cart'), 'cart'],
  ['coupons', 'Coupons', tl('demo.screen.coupons'), 'coupons'],
  ['checkout', 'Checkout', tl('demo.screen.checkout'), 'checkout'],
  ['complete', 'OrderComplete', tl('demo.screen.complete'), 'order-complete'],
  ['orders', 'OrderHistory', tl('demo.screen.orders'), 'order-history'],
  ['order', 'OrderDetail', tl('demo.screen.order'), 'order-detail'],
  ['mypage', 'MyPage', tl('demo.screen.mypage'), 'my-page'],
  ['address', 'AddressList', tl('demo.screen.address'), 'address-list'],
  ['addressEdit', 'AddressEdit', tl('demo.screen.addressEdit'), 'address-edit'],
  ['payment', 'PaymentMethods', tl('demo.screen.payment'), 'payment-methods'],
  ['notices', 'Notifications', tl('demo.screen.notices'), 'notifications'],
  ['settings', 'Settings', tl('demo.screen.settings'), 'settings'],
  ['help', 'Help', tl('demo.screen.help'), 'help'],
  ['top', 'Top', tl('demo.screen.top'), 'top', 'doc'],
  ['start', 'GettingStarted', tl('demo.screen.start'), 'getting-started', 'doc'],
  ['components', 'ComponentList', tl('demo.screen.components'), 'component-list', 'doc'],
  ['component', 'ComponentDetail', tl('demo.screen.component'), 'component-detail', 'doc'],
  ['attrs', 'AttributeReference', tl('demo.screen.attrs'), 'attribute-reference', 'doc'],
  ['anatomy', 'SpecAnatomy', tl('demo.screen.anatomy'), 'spec-anatomy', 'doc'],
];
/* The spec files shown on the whiteboard (demo content in the screen_spec format). Counted items per section:
   structure.components, stateManagement.uiVariables, dataFlow.viewModel.methods, userActions, transitions
   and branchContracts branches. */
const SPEC_DOCS = {
  login: {
    metadata: { name: 'Login', displayName: tl('demo.screen.login'), description: tl('demo.spec.log.email.password'), platforms: ['ios', 'android', 'web'], layoutFile: 'login', createdAt: '2026-10-17' },
    components: [['View', 'login_root', tl('demo.spec.container.whole.screen')], ['Label', 'title_label', tl('demo.spec.screen.title.log')], ['TextField', 'email_input', tl('demo.spec.email.field')], ['TextField', 'password_input', tl('demo.spec.password.field.masked')], ['Label', 'error_label', tl('demo.spec.input.sign.errors')], ['Button', 'login_button', tl('demo.spec.logs')], ['Indicator', 'loading_indicator', tl('demo.spec.shown.while.connecting')], ['Button', 'forgot_button', tl('demo.spec.password.reset')], ['Button', 'signup_button', tl('demo.spec.sign.up')]],
    layoutChildren: ['title_label', 'email_input', 'password_input', 'error_label', 'login_button', 'loading_indicator', 'forgot_button', 'signup_button'],
    uiVariables: [['email', 'String', '""'], ['password', 'String', '""'], ['isLoading', 'Bool', 'false'], ['errorMessage', 'String?', 'null']],
    eventHandlers: [['onLoginTap', tl('demo.spec.validate.input.then.call.login')], ['onSignupTap', tl('demo.spec.go.signup.screen')]],
    vmMethods: ['login()', 'validateEmail(_:)', 'validatePassword(_:)', 'clearError()', 'openSignup()'],
    vmVars: ['email', 'password', 'isLoading', 'errorMessage'],
    repositories: ['AuthRepository'],
    apis: [['postLogin', 'POST', '/auth/login']],
    userActions: [[tl('demo.spec.tap.login.button'), 'onLoginTap → login()'], [tl('demo.spec.tap.forgot.password'), tl('demo.spec.go.reset.screen')], [tl('demo.spec.tap.sign.up'), 'onSignupTap']],
    transitions: [[tl('demo.spec.login.succeeds'), 'Home'], [tl('demo.spec.tap.signup.button'), 'Signup']],
    branches: [['login', tl('demo.spec.email.empty'), tl('demo.spec.error.label.enter.your.email')], ['login', tl('demo.spec.password.under.8.characters'), tl('demo.spec.error.label.at.least.8')], ['login', tl('demo.spec.api.returns.401'), tl('demo.spec.error.label.shows.sign.error')], ['login', tl('demo.spec.api.returns.200'), tl('demo.spec.go.home')]],
  },
  home: {
    metadata: { name: 'Home', displayName: tl('demo.screen.home'), description: tl('demo.spec.shows.picks.categories.way.into'), platforms: ['ios', 'android', 'web'], layoutFile: 'home', createdAt: '2026-10-12' },
    components: [['SafeAreaView', 'home_root', tl('demo.spec.whole.screen')], ['View', 'header_view', tl('demo.spec.header')], ['Label', 'greeting_label', tl('demo.spec.greeting')], ['Button', 'cart_button', tl('demo.spec.cart')], ['Label', 'cart_badge', tl('demo.spec.items.cart')], ['TextField', 'search_input', tl('demo.spec.product.search')], ['Collection', 'banner_collection', tl('demo.spec.campaign.banners')], ['Label', 'category_title', tl('demo.spec.category.heading')], ['Collection', 'category_collection', tl('demo.spec.categories')], ['Label', 'recommend_title', tl('demo.spec.picks.heading')], ['Collection', 'recommend_collection', tl('demo.spec.recommended.products')], ['Indicator', 'loading_indicator', tl('demo.spec.loading')]],
    layoutChildren: ['header_view', 'search_input', 'banner_collection', 'category_title', 'category_collection', 'recommend_title', 'recommend_collection', 'loading_indicator'],
    uiVariables: [['userName', 'String', '""'], ['cartCount', 'Int', '0'], ['searchText', 'String', '""'], ['isLoading', 'Bool', 'true'], ['banners', '[Banner]', '[]']],
    eventHandlers: [['onCartTap', tl('demo.spec.cart.screen')], ['onSearchSubmit', tl('demo.spec.search.results')], ['onProductTap', tl('demo.spec.product.details')]],
    vmMethods: ['onAppear()', 'loadHome()', 'refresh()', 'openCart()', 'search(_:)', 'openProduct(_:)'],
    vmVars: ['userName', 'cartCount', 'banners', 'categories', 'recommends', 'isLoading'],
    repositories: ['HomeRepository', 'CartRepository'],
    apis: [['getHome', 'GET', '/home'], ['getCartSummary', 'GET', '/cart/summary']],
    userActions: [[tl('demo.spec.tap.cart.button'), 'onCartTap → openCart()'], [tl('demo.spec.submit.search'), 'onSearchSubmit → search(_:)'], [tl('demo.spec.tap.recommended.product'), 'onProductTap → openProduct(_:)'], [tl('demo.spec.pull.refresh'), 'refresh()']],
    transitions: [['openCart()', 'Cart'], ['openProduct(_:)', 'ProductDetail']],
    branches: [['loadHome', tl('demo.spec.api.succeeds'), tl('demo.spec.show.banners.recommends')], ['loadHome', tl('demo.spec.api.fails'), tl('demo.spec.show.error.retry.button')], ['openCart', 'cartCount == 0', tl('demo.spec.open.empty.cart')]],
  },
  cart: {
    metadata: { name: 'Cart', displayName: tl('demo.screen.cart'), description: tl('demo.spec.review.cart.apply.coupon.go'), platforms: ['ios', 'android', 'web'], layoutFile: 'cart', createdAt: '2026-10-08' },
    components: [['SafeAreaView', 'cart_root', tl('demo.spec.whole.screen')], ['Label', 'title_label', tl('demo.spec.screen.title.cart')], ['Collection', 'cart_list', tl('demo.spec.products.cart.cart.item')], ['Label', 'empty_label', tl('demo.spec.message.empty.cart')], ['Label', 'stock_warning', tl('demo.spec.out.stock.warning')], ['TextField', 'coupon_input', tl('demo.spec.coupon.code')], ['Button', 'coupon_apply', tl('demo.spec.apply.coupon')], ['Label', 'coupon_error', tl('demo.spec.coupon.error')], ['Label', 'total_label', tl('demo.spec.total.price')], ['Button', 'checkout_button', tl('demo.spec.buy')]],
    layoutChildren: ['title_label', 'cart_list', 'empty_label', 'stock_warning', 'coupon_input', 'coupon_apply', 'coupon_error', 'total_label', 'checkout_button'],
    uiVariables: [['items', '[CartItem]', '[]'], ['isEmpty', 'Bool', 'true'], ['couponCode', 'String', '""'], ['couponError', 'String?', 'null'], ['total', 'Int', '0'], ['canCheckout', 'Bool', 'false']],
    eventHandlers: [['onQuantityChange', tl('demo.spec.change.quantity')], ['onApplyCoupon', tl('demo.spec.apply.coupon')], ['onCheckoutTap', tl('demo.spec.proceed.checkout')]],
    vmMethods: ['loadCart()', 'changeQuantity(_:qty:)', 'applyCoupon(_:)', 'removeItem(_:)', 'recalcTotal()', 'checkout()', 'placeOrder()'],
    vmVars: ['items', 'isEmpty', 'couponCode', 'couponError', 'total', 'canCheckout'],
    repositories: ['CartRepository', 'OrderRepository'],
    apis: [['getCart', 'GET', '/cart'], ['postCoupon', 'POST', '/cart/coupon'], ['postOrder', 'POST', '/orders']],
    userActions: [[tl('demo.spec.change.quantity'), 'onQuantityChange → changeQuantity'], [tl('demo.spec.apply.coupon'), 'onApplyCoupon → applyCoupon'], [tl('demo.spec.remove.item'), 'removeItem'], [tl('demo.spec.tap.buy'), 'onCheckoutTap → checkout()'], [tl('demo.spec.confirm.purchase'), 'placeOrder()']],
    transitions: [[tl('demo.spec.checkout.signed.out'), 'Login'], [tl('demo.spec.placeorder.succeeds'), 'OrderComplete'], [tl('demo.spec.tap.product'), 'ProductDetail']],
    branches: [['loadCart', 'items.count > 0', tl('demo.spec.show.cart.list')], ['changeQuantity', 'qty == 0', tl('demo.spec.remove.row')], ['loadCart', 'isEmpty == true', tl('demo.spec.disable.checkout.button')], ['applyCoupon', 'valid', tl('demo.spec.show.discount.label')], ['applyCoupon', 'expired', tl('demo.spec.show.coupon.error')], ['loadCart', 'item.stock == 0', tl('demo.spec.show.stock.warning')], ['checkout', tl('demo.spec.signed.out'), tl('demo.spec.go.login')], ['placeOrder', 'success', tl('demo.spec.go.ordercomplete')]],
  },
  list: {
    metadata: { name: 'ProductList', displayName: tl('demo.screen.list'), description: tl('demo.spec.lists.products.sorting.filters'), platforms: ['ios', 'android', 'web'], layoutFile: 'product-list', createdAt: '2026-10-02' },
    components: [['SafeAreaView', 'list_root', tl('demo.spec.whole.screen')], ['TextField', 'search_input', tl('demo.screen.filter')], ['Segment', 'sort_segment', tl('demo.spec.sort')], ['Collection', 'product_collection', tl('demo.spec.product.list.product.cell')], ['Label', 'result_count', tl('demo.spec.result.count')], ['Indicator', 'loading_indicator', tl('demo.spec.loading')], ['Label', 'empty_label', tl('demo.spec.no.matches')], ['Button', 'filter_button', tl('demo.spec.filter.options')]],
    layoutChildren: ['search_input', 'sort_segment', 'filter_button', 'result_count', 'product_collection', 'loading_indicator', 'empty_label'],
    uiVariables: [['products', '[Product]', '[]'], ['query', 'String', '""'], ['sort', 'SortOrder', '.popular'], ['isLoading', 'Bool', 'true']],
    eventHandlers: [['onSortChange', tl('demo.spec.change.sort')], ['onProductTap', tl('demo.spec.product.details')]],
    vmMethods: ['load()', 'loadMore()', 'changeSort(_:)', 'search(_:)', 'openProduct(_:)'],
    vmVars: ['products', 'query', 'sort', 'isLoading'],
    repositories: ['ProductRepository'],
    apis: [['listProducts', 'GET', '/products']],
    userActions: [[tl('demo.spec.change.sort'), 'onSortChange → changeSort'], [tl('demo.spec.scroll.end'), 'loadMore()'], [tl('demo.spec.tap.product'), 'onProductTap → openProduct']],
    transitions: [['openProduct(_:)', 'ProductDetail'], [tl('demo.spec.tap.filter.button'), 'FilterSheet']],
    branches: [['load', tl('demo.spec.no.results'), tl('demo.spec.show.empty.label')], ['load', tl('demo.spec.api.fails'), tl('demo.spec.show.error')], ['loadMore', tl('demo.spec.last.page'), tl('demo.spec.stop.loading.more')], ['changeSort', 'price', tl('demo.spec.sort.price')], ['search', tl('demo.spec.query.empty'), tl('demo.spec.show.everything')]],
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
  onboarding: doc('onboarding', tl('demo.spec.introduces.app.3.slides.asks'), '2026-09-20',
    `SafeAreaView onboarding_root ${tl('demo.spec.whole.screen')}|Collection slide_pager ${tl('demo.spec.intro.slides.3')}|View page_dots ${tl('demo.spec.current.page')}|Button next_button ${tl('demo.spec.next')}|Button skip_button ${tl('demo.spec.skip')}|Button start_button ${tl('demo.spec.get.started')}`,
    { vars: [['page', 'Int', '0'], ['isLastPage', 'Bool', 'false']], handlers: [['onNextTap', tl('demo.spec.next.slide')], ['onStartTap', tl('demo.spec.ask.notifications.then.go.home')]],
      methods: ['next()', 'skip()', 'start()', 'requestNotification()'], repos: ['SettingsRepository'], apis: [],
      actions: [[tl('demo.spec.tap.next'), 'onNextTap → next()'], [tl('demo.spec.tap.skip'), 'skip()'], [tl('demo.spec.tap.get.started'), 'onStartTap → start()']],
      transitions: [['start()', 'Home'], ['skip()', 'Home']],
      branches: [['next', tl('demo.spec.last.slide'), tl('demo.spec.show.start.button')], ['start', tl('demo.spec.notifications.denied'), tl('demo.spec.go.home.2')]] }),
  signup: doc('signup', tl('demo.spec.create.account.email.password'), '2026-10-17',
    `SafeAreaView signup_root ${tl('demo.spec.whole.screen')}|Label title_label ${tl('demo.spec.screen.title.sign.up')}|TextField name_input ${tl('demo.spec.name')}|TextField email_input ${tl('demo.spec.email')}|TextField password_input ${tl('demo.spec.password.8.characters')}|CheckBox terms_check ${tl('demo.spec.agree.terms')}|Label error_label ${tl('demo.spec.input.error')}|Button signup_button ${tl('demo.spec.sign.up.2')}|Button login_link ${tl('demo.spec.back.login')}|Indicator loading_indicator ${tl('demo.spec.shown.while.connecting')}`,
    { vars: [['name', 'String', '""'], ['email', 'String', '""'], ['password', 'String', '""'], ['agreed', 'Bool', 'false'], ['errorMessage', 'String?', 'null'], ['isLoading', 'Bool', 'false']],
      handlers: [['onSignupTap', tl('demo.spec.validate.input.then.call.signup')], ['onTermsToggle', tl('demo.spec.toggle.agreement')]],
      methods: ['signup()', 'validate()', 'toggleTerms()', 'openLogin()'], repos: ['AuthRepository'], apis: [['postSignup', 'POST', '/auth/signup']],
      actions: [[tl('demo.spec.tap.sign.up.2'), 'onSignupTap → signup()'], [tl('demo.spec.agree.terms'), 'onTermsToggle → toggleTerms()'], [tl('demo.spec.tap.back.login'), 'openLogin()']],
      transitions: [[tl('demo.spec.signup.succeeds'), 'Home'], [tl('demo.spec.tap.login.link'), 'Login']],
      branches: [['signup', tl('demo.spec.terms.not.accepted'), tl('demo.spec.disable.signup.button')], ['signup', tl('demo.spec.email.already.registered'), tl('demo.spec.error.label.already.registered')], ['signup', tl('demo.spec.password.under.8.characters'), tl('demo.spec.error.label.at.least.8')], ['signup', tl('demo.spec.api.returns.201'), tl('demo.spec.go.home')]] }),
  search: doc('search', tl('demo.spec.search.products.keyword.history.suggestions'), '2026-09-28',
    `SafeAreaView search_root ${tl('demo.spec.whole.screen')}|TextField search_input ${tl('demo.spec.keyword')}|Button cancel_button ${tl('demo.spec.cancel')}|Collection history_list ${tl('demo.spec.search.history')}|Collection suggest_list ${tl('demo.spec.suggestions')}|Button clear_history ${tl('demo.spec.clear.history')}`,
    { vars: [['query', 'String', '""'], ['history', '[String]', '[]'], ['suggestions', '[String]', '[]']], handlers: [['onSubmit', tl('demo.spec.submit.search')], ['onClearHistory', tl('demo.spec.clear.history')]],
      methods: ['loadHistory()', 'suggest(_:)', 'submit()', 'clearHistory()'], repos: ['SearchRepository'], apis: [['getSuggestions', 'GET', '/search/suggest']],
      actions: [[tl('demo.spec.type.keyword'), 'suggest(_:)'], [tl('demo.spec.submit.search'), 'onSubmit → submit()'], [tl('demo.spec.tap.clear.history'), 'onClearHistory → clearHistory()']],
      transitions: [['submit()', 'ProductList'], [tl('demo.spec.tap.cancel.button'), 'Home']],
      branches: [['suggest', tl('demo.spec.query.empty'), tl('demo.spec.show.history')], ['suggest', tl('demo.spec.no.suggestions'), tl('demo.spec.show.no.suggestions')], ['submit', tl('demo.spec.query.empty'), tl('demo.spec.do.nothing')]] }),
  filter: doc('filter', tl('demo.spec.sheet.filter.list.price.category'), '2026-09-30',
    `View filter_root ${tl('demo.spec.whole.sheet')}|Label title_label ${tl('demo.spec.heading.filter')}|SelectBox category_select ${tl('demo.spec.category')}|View price_range ${tl('demo.spec.price.range')}|Switch stock_switch ${tl('demo.spec.stock.only')}|Button reset_button ${tl('demo.spec.reset')}|Button apply_button ${tl('demo.spec.apply')}`,
    { vars: [['category', 'String?', 'null'], ['minPrice', 'Int', '0'], ['maxPrice', 'Int', '50000'], ['inStockOnly', 'Bool', 'false']], handlers: [['onApplyTap', tl('demo.spec.return.filters.close')], ['onResetTap', tl('demo.spec.reset.filters')]],
      methods: ['apply()', 'reset()', 'setPrice(min:max:)'], repos: ['CategoryRepository'], apis: [['listCategories', 'GET', '/categories']],
      actions: [[tl('demo.spec.tap.apply'), 'onApplyTap → apply()'], [tl('demo.spec.tap.reset'), 'onResetTap → reset()']],
      transitions: [['apply()', 'ProductList']],
      branches: [['apply', 'minPrice > maxPrice', tl('demo.spec.swap.prices')], ['reset', '—', tl('demo.spec.reset.all.filters')]] }),
  detail: doc('detail', tl('demo.spec.shows.product.s.photos.price'), '2026-10-14',
    `SafeAreaView detail_root ${tl('demo.spec.whole.screen')}|Image product_image ${tl('demo.spec.product.photo')}|Label name_label ${tl('demo.spec.product.name')}|Label price_label ${tl('demo.spec.price')}|Label stock_label ${tl('demo.spec.stock.status')}|Segment size_segment ${tl('demo.spec.size.picker')}|Button add_cart_button ${tl('demo.spec.add.cart')}|Button favorite_button ${tl('demo.screen.favorites')}|Label review_summary ${tl('demo.spec.average.rating.count')}|Button reviews_button ${tl('demo.spec.see.reviews')}|Indicator loading_indicator ${tl('demo.spec.loading')}`,
    { vars: [['product', 'Product?', 'null'], ['size', 'Int', '-1'], ['isFavorite', 'Bool', 'false'], ['canAddToCart', 'Bool', 'false'], ['isLoading', 'Bool', 'true']],
      handlers: [['onAddCartTap', tl('demo.spec.add.cart.2')], ['onFavoriteTap', tl('demo.spec.toggle.favorite')], ['onSizeChange', tl('demo.spec.pick.size')]],
      methods: ['onAppear()', 'loadProduct()', 'selectSize(_:)', 'addToCart()', 'toggleFavorite()', 'openReviews()'], repos: ['ProductRepository', 'CartRepository', 'FavoriteRepository'],
      apis: [['getProduct', 'GET', '/products/{id}'], ['postCartItem', 'POST', '/cart/items'], ['putFavorite', 'PUT', '/favorites/{id}']],
      actions: [[tl('demo.spec.pick.size'), 'onSizeChange → selectSize(_:)'], [tl('demo.spec.tap.add.cart'), 'onAddCartTap → addToCart()'], [tl('demo.spec.tap.favorite'), 'onFavoriteTap → toggleFavorite()'], [tl('demo.spec.tap.see.reviews'), 'openReviews()']],
      transitions: [[tl('demo.spec.addtocart.succeeds'), 'Cart'], ['openReviews()', 'Reviews']],
      branches: [['loadProduct', 'stock == 0', tl('demo.spec.disable.add.cart.button.show')], ['addToCart', tl('demo.spec.no.size.picked'), tl('demo.spec.highlight.size.segment')], ['addToCart', tl('demo.spec.api.succeeds'), tl('demo.spec.go.cart')], ['toggleFavorite', tl('demo.spec.signed.out'), tl('demo.spec.go.login')]] }),
  reviews: doc('reviews', tl('demo.spec.shows.product.s.reviews.newest'), '2026-10-06',
    `SafeAreaView reviews_root ${tl('demo.spec.whole.screen')}|Label average_label ${tl('demo.spec.average.rating')}|Segment star_filter ${tl('demo.spec.filter.rating')}|Collection review_list ${tl('demo.spec.review.list')}|Indicator loading_indicator ${tl('demo.spec.loading')}|Label empty_label ${tl('demo.spec.no.reviews')}`,
    { vars: [['reviews', '[Review]', '[]'], ['stars', 'Int?', 'null'], ['isLoading', 'Bool', 'true']], handlers: [['onStarFilter', tl('demo.spec.filter.rating.2')]],
      methods: ['load()', 'loadMore()', 'filter(stars:)'], repos: ['ReviewRepository'], apis: [['listReviews', 'GET', '/products/{id}/reviews']],
      actions: [[tl('demo.spec.filter.rating.2'), 'onStarFilter → filter(stars:)'], [tl('demo.spec.scroll.end'), 'loadMore()']],
      transitions: [[tl('demo.spec.back'), 'ProductDetail']],
      branches: [['load', tl('demo.spec.none'), tl('demo.spec.show.empty.label')], ['loadMore', tl('demo.spec.last.page'), tl('demo.spec.stop.loading.more')], ['filter', 'stars == nil', tl('demo.spec.show.everything')]] }),
  favorites: doc('favorites', tl('demo.spec.lists.favorite.products.move.them'), '2026-09-26',
    `SafeAreaView favorites_root ${tl('demo.spec.whole.screen')}|Collection favorite_list ${tl('demo.spec.favorites.list')}|Label empty_label ${tl('demo.spec.no.favorites')}|Button edit_button ${tl('demo.spec.edit')}`,
    { vars: [['items', '[Product]', '[]'], ['isEditing', 'Bool', 'false']], handlers: [['onRemove', tl('demo.spec.remove.from.favorites')], ['onEditTap', tl('demo.spec.toggle.edit.mode')]],
      methods: ['load()', 'remove(_:)', 'moveToCart(_:)'], repos: ['FavoriteRepository'], apis: [['listFavorites', 'GET', '/favorites'], ['deleteFavorite', 'DELETE', '/favorites/{id}']],
      actions: [[tl('demo.spec.tap.product'), tl('demo.spec.open.product.details')], [tl('demo.spec.tap.remove'), 'onRemove → remove(_:)'], [tl('demo.spec.tap.cart'), 'moveToCart(_:)']],
      transitions: [[tl('demo.spec.tap.product'), 'ProductDetail']],
      branches: [['load', tl('demo.spec.none'), tl('demo.spec.show.empty.label')], ['remove', tl('demo.spec.last.one'), tl('demo.spec.switch.empty.label')]] }),
  checkout: doc('checkout', tl('demo.spec.confirm.address.payment.then.place'), '2026-10-09',
    `SafeAreaView checkout_root ${tl('demo.spec.whole.screen')}|Label address_label ${tl('demo.screen.address')}|Button address_change ${tl('demo.spec.change.address')}|Label payment_label ${tl('demo.screen.payment')}|Button payment_change ${tl('demo.spec.change.payment.method')}|Label subtotal_label ${tl('demo.spec.subtotal')}|Label shipping_label ${tl('demo.spec.shipping')}|Label total_label ${tl('demo.spec.total')}|Button confirm_button ${tl('demo.spec.place.order')}|Indicator loading_indicator ${tl('demo.spec.sending')}`,
    { vars: [['address', 'Address?', 'null'], ['payment', 'Payment?', 'null'], ['total', 'Int', '0'], ['canConfirm', 'Bool', 'false'], ['isSubmitting', 'Bool', 'false']],
      handlers: [['onConfirmTap', tl('demo.spec.send.order')], ['onChangeAddress', tl('demo.spec.address.selection')]],
      methods: ['load()', 'changeAddress()', 'changePayment()', 'confirm()', 'recalc()'], repos: ['OrderRepository', 'AddressRepository'], apis: [['getCheckout', 'GET', '/checkout'], ['postOrder', 'POST', '/orders']],
      actions: [[tl('demo.spec.tap.place.order'), 'onConfirmTap → confirm()'], [tl('demo.spec.change.address'), 'onChangeAddress → changeAddress()'], [tl('demo.spec.change.payment.method'), 'changePayment()']],
      transitions: [[tl('demo.spec.confirm.succeeds'), 'OrderComplete'], ['changeAddress()', 'AddressList'], ['changePayment()', 'PaymentMethods']],
      branches: [['load', 'address == nil', tl('demo.spec.disable.confirm.button')], ['confirm', tl('demo.spec.out.stock'), tl('demo.spec.show.error.go.cart')], ['confirm', tl('demo.spec.payment.error'), tl('demo.spec.highlight.payment.label')], ['confirm', 'success', tl('demo.spec.go.ordercomplete')]] }),
  complete: doc('complete', tl('demo.spec.shows.order.number.delivery.date'), '2026-10-10',
    `SafeAreaView complete_root ${tl('demo.spec.whole.screen')}|Image done_image ${tl('demo.spec.done.illustration')}|Label order_number ${tl('demo.spec.order.number')}|Label delivery_label ${tl('demo.spec.delivery.date')}|Button orders_button ${tl('demo.spec.see.order.history')}|Button home_button ${tl('demo.spec.keep.shopping')}`,
    { vars: [['orderNumber', 'String', '""'], ['deliveryDate', 'String', '""']], handlers: [['onHomeTap', tl('demo.spec.back.home')]],
      methods: ['onAppear()', 'openOrders()', 'backToHome()'], repos: ['OrderRepository'], apis: [['getOrder', 'GET', '/orders/{id}']],
      actions: [[tl('demo.spec.tap.see.order.history'), 'openOrders()'], [tl('demo.spec.tap.keep.shopping'), 'onHomeTap → backToHome()']],
      transitions: [['openOrders()', 'OrderHistory'], ['backToHome()', 'Home']],
      branches: [['onAppear', tl('demo.spec.fetching.order.fails'), tl('demo.spec.show.only.order.number')], ['onAppear', 'success', tl('demo.spec.show.delivery.date')]] }),
  orders: doc('orders', tl('demo.spec.lists.past.orders.newest.first'), '2026-10-13',
    `SafeAreaView orders_root ${tl('demo.spec.whole.screen')}|Segment period_segment ${tl('demo.spec.period.3.months.1.year')}|Collection order_list ${tl('demo.spec.order.list')}|Label empty_label ${tl('demo.spec.no.orders')}|Indicator loading_indicator ${tl('demo.spec.loading')}`,
    { vars: [['orders', '[Order]', '[]'], ['period', 'Int', '0'], ['isLoading', 'Bool', 'true']], handlers: [['onPeriodChange', tl('demo.spec.change.period')], ['onOrderTap', tl('demo.spec.order.details')]],
      methods: ['load()', 'loadMore()', 'changePeriod(_:)', 'openOrder(_:)'], repos: ['OrderRepository'], apis: [['listOrders', 'GET', '/orders']],
      actions: [[tl('demo.spec.change.period'), 'onPeriodChange → changePeriod(_:)'], [tl('demo.spec.tap.order'), 'onOrderTap → openOrder(_:)'], [tl('demo.spec.scroll.end'), 'loadMore()']],
      transitions: [['openOrder(_:)', 'OrderDetail']],
      branches: [['load', tl('demo.spec.none'), tl('demo.spec.show.empty.label')], ['loadMore', tl('demo.spec.last.page'), tl('demo.spec.stop.loading.more')]] }),
  order: doc('order', tl('demo.spec.shows.one.order.s.items'), '2026-10-16',
    `SafeAreaView order_root ${tl('demo.spec.whole.screen')}|Label status_label ${tl('demo.spec.shipping.status')}|Collection item_list ${tl('demo.spec.ordered.items')}|Label total_label ${tl('demo.spec.total')}|Label address_label ${tl('demo.screen.address')}|Button receipt_button ${tl('demo.spec.receipt')}|Button cancel_button ${tl('demo.spec.cancel.order')}`,
    { vars: [['order', 'Order?', 'null'], ['canCancel', 'Bool', 'false'], ['isLoading', 'Bool', 'true']], handlers: [['onCancelTap', tl('demo.spec.confirm.cancellation')], ['onReceiptTap', tl('demo.spec.open.receipt')]],
      methods: ['load()', 'cancel()', 'openReceipt()'], repos: ['OrderRepository'], apis: [['getOrder', 'GET', '/orders/{id}'], ['postCancel', 'POST', '/orders/{id}/cancel']],
      actions: [[tl('demo.spec.tap.cancel.order'), 'onCancelTap → cancel()'], [tl('demo.spec.tap.receipt'), 'onReceiptTap → openReceipt()']],
      transitions: [[tl('demo.spec.tap.product'), 'ProductDetail']],
      branches: [['load', tl('demo.spec.shipped'), tl('demo.spec.hide.cancel.button')], ['cancel', 'success', tl('demo.spec.set.status.label.canceled')]] }),
  mypage: doc('mypage', tl('demo.spec.account.info.way.into.settings'), '2026-09-24',
    `SafeAreaView mypage_root ${tl('demo.spec.whole.screen')}|Image avatar_image ${tl('demo.spec.avatar')}|Label name_label ${tl('demo.spec.name')}|Button orders_button ${tl('demo.screen.orders')}|Button favorites_button ${tl('demo.screen.favorites')}|Button address_button ${tl('demo.screen.address')}|Button payment_button ${tl('demo.screen.payment')}|Button settings_button ${tl('demo.screen.settings')}|Button logout_button ${tl('demo.spec.log.out')}`,
    { vars: [['userName', 'String', '""'], ['avatarUrl', 'String?', 'null']], handlers: [['onLogoutTap', tl('demo.spec.confirm.logout')]],
      methods: ['load()', 'logout()', 'open(_:)'], repos: ['UserRepository', 'AuthRepository'], apis: [['getMe', 'GET', '/me'], ['postLogout', 'POST', '/auth/logout']],
      actions: [[tl('demo.spec.tap.menu.item'), 'open(_:)'], [tl('demo.spec.tap.log.out'), 'onLogoutTap → logout()']],
      transitions: [[tl('demo.spec.tap.orders.button'), 'OrderHistory'], [tl('demo.spec.tap.favorites.button'), 'Favorites'], [tl('demo.spec.tap.settings.button'), 'Settings'], [tl('demo.spec.logout.succeeds'), 'Login']],
      branches: [['logout', tl('demo.spec.canceled.at.prompt'), tl('demo.spec.do.nothing')], ['load', tl('demo.spec.signed.out'), tl('demo.spec.go.login')]] }),
  address: doc('address', tl('demo.spec.lists.saved.addresses.pick.default'), '2026-10-15',
    `SafeAreaView address_root ${tl('demo.spec.whole.screen')}|Collection address_list ${tl('demo.spec.address.list')}|Button add_button ${tl('demo.spec.add.address')}|Label empty_label ${tl('demo.spec.none.saved')}`,
    { vars: [['addresses', '[Address]', '[]'], ['selectedId', 'String?', 'null']], handlers: [['onSelect', tl('demo.spec.make.default')], ['onAddTap', tl('demo.spec.add')]],
      methods: ['load()', 'select(_:)', 'add()', 'edit(_:)'], repos: ['AddressRepository'], apis: [['listAddresses', 'GET', '/addresses'], ['putDefault', 'PUT', '/addresses/{id}/default']],
      actions: [[tl('demo.spec.tap.address'), 'onSelect → select(_:)'], [tl('demo.spec.tap.add'), 'onAddTap → add()'], [tl('demo.spec.tap.edit'), 'edit(_:)']],
      transitions: [['add()', 'AddressEdit'], ['edit(_:)', 'AddressEdit']],
      branches: [['load', tl('demo.spec.none'), tl('demo.spec.show.empty.label.add.button')], ['select', tl('demo.spec.came.from.checkout'), tl('demo.spec.pick.one.return.checkout')]] }),
  settings: doc('settings', tl('demo.spec.notification.display.account.settings'), '2026-09-22',
    `SafeAreaView settings_root ${tl('demo.spec.whole.screen')}|Switch push_switch ${tl('demo.spec.push.notifications')}|Switch mail_switch ${tl('demo.spec.newsletter')}|SelectBox theme_select ${tl('demo.spec.display.mode')}|Button help_button ${tl('demo.screen.help')}|Button delete_button ${tl('demo.spec.delete.account')}`,
    { vars: [['pushEnabled', 'Bool', 'true'], ['mailEnabled', 'Bool', 'false'], ['theme', 'String', '"system"']], handlers: [['onPushToggle', tl('demo.spec.toggle.notifications')], ['onDeleteTap', tl('demo.spec.confirm.deletion')]],
      methods: ['load()', 'togglePush()', 'toggleMail()', 'setTheme(_:)', 'deleteAccount()'], repos: ['SettingsRepository'], apis: [['getSettings', 'GET', '/settings'], ['putSettings', 'PUT', '/settings']],
      actions: [[tl('demo.spec.toggle.push.notifications'), 'onPushToggle → togglePush()'], [tl('demo.spec.pick.display.mode'), 'setTheme(_:)'], [tl('demo.spec.tap.delete.account'), 'onDeleteTap → deleteAccount()']],
      transitions: [[tl('demo.spec.tap.help.button'), 'Help']],
      branches: [['togglePush', tl('demo.spec.notifications.denied.os'), tl('demo.spec.show.how.open.settings.app')], ['deleteAccount', 'success', tl('demo.spec.go.login')]] }),
});
/* The documentation site (docs-site/) is a JsonUI project of its own. */
Object.assign(SPEC_DOCS, {
  top: doc('top', tl('demo.spec.introduces.jsonui.links.getting.started'), '2026-09-10',
    `SafeAreaView top_root ${tl('demo.spec.whole.screen')}|Label hero_title ${tl('demo.spec.heading')}|Label hero_lead ${tl('demo.spec.intro.text')}|Button start_button ${tl('demo.spec.get.started')}|Collection platform_cards ${tl('demo.spec.ios.android.web.guides')}|Collection news_list ${tl('demo.spec.news')}`,
    { vars: [['news', '[News]', '[]'], ['isLoading', 'Bool', 'true']], handlers: [['onStartTap', tl('demo.spec.getting.started')]],
      methods: ['load()', 'openStart()', 'openPlatform(_:)'], repos: ['DocsRepository'], apis: [['getNews', 'GET', '/news.json']],
      actions: [[tl('demo.spec.tap.get.started'), 'onStartTap → openStart()'], [tl('demo.spec.pick.platform'), 'openPlatform(_:)']],
      transitions: [['openStart()', 'GettingStarted'], ['openPlatform(_:)', 'GettingStarted']],
      branches: [['load', tl('demo.spec.no.news'), tl('demo.spec.hide.news.list')], ['openPlatform', 'web', tl('demo.spec.open.web.steps')]] }),
  start: doc('start', tl('demo.spec.steps.from.install.your.first'), '2026-09-12',
    `SafeAreaView start_root ${tl('demo.spec.whole.screen')}|Segment platform_tabs ${tl('demo.spec.ios.android.web.switch')}|Collection step_list ${tl('demo.spec.steps')}|Label code_sample ${tl('demo.spec.code.sample')}|Button copy_button ${tl('demo.spec.copy')}|Button next_button ${tl('demo.spec.next')}`,
    { vars: [['platform', 'String', '"ios"'], ['copied', 'Bool', 'false']], handlers: [['onPlatformChange', tl('demo.spec.switch.platforms')], ['onCopyTap', tl('demo.spec.copy.code')]],
      methods: ['selectPlatform(_:)', 'copyCode()', 'openNext()'], repos: [], apis: [],
      actions: [[tl('demo.spec.switch.platforms'), 'onPlatformChange → selectPlatform(_:)'], [tl('demo.spec.tap.copy'), 'onCopyTap → copyCode()']],
      transitions: [['openNext()', 'ComponentList']],
      branches: [['copyCode', 'success', tl('demo.spec.show.copied')]] }),
  components: doc('components', tl('demo.spec.lists.components.category.linking.their'), '2026-09-18',
    `SafeAreaView list_root ${tl('demo.spec.whole.screen')}|TextField filter_input ${tl('demo.screen.filter')}|Segment category_tabs ${tl('demo.spec.category.tabs')}|Collection component_grid ${tl('demo.screen.components')}|Label empty_label ${tl('demo.spec.no.matches')}`,
    { vars: [['query', 'String', '""'], ['category', 'String', '"all"'], ['components', '[Component]', '[]']], handlers: [['onComponentTap', tl('demo.spec.details')]],
      methods: ['load()', 'filter(_:)', 'selectCategory(_:)', 'openComponent(_:)'], repos: ['DocsRepository'], apis: [['listComponents', 'GET', '/components.json']],
      actions: [[tl('demo.spec.filter'), 'filter(_:)'], [tl('demo.spec.pick.category'), 'selectCategory(_:)'], [tl('demo.spec.tap.component'), 'onComponentTap → openComponent(_:)']],
      transitions: [['openComponent(_:)', 'ComponentDetail']],
      branches: [['filter', tl('demo.spec.none'), tl('demo.spec.show.empty.label')], ['selectCategory', 'all', tl('demo.spec.show.everything')]] }),
  component: doc('component', tl('demo.spec.shows.one.component.s.attributes'), '2026-10-01',
    `SafeAreaView detail_root ${tl('demo.spec.whole.screen')}|Label name_label ${tl('demo.spec.component.name')}|Label summary_label ${tl('demo.spec.summary')}|Collection attr_table ${tl('demo.spec.attribute.table')}|Label sample_code ${tl('demo.spec.json.example')}|Segment preview_tabs ${tl('demo.spec.preview.switch')}`,
    { vars: [['component', 'Component?', 'null'], ['preview', 'String', '"ios"']], handlers: [['onAttrTap', tl('demo.spec.attribute.reference')]],
      methods: ['load()', 'selectPreview(_:)', 'openAttribute(_:)'], repos: ['DocsRepository'], apis: [['getComponent', 'GET', '/components/{name}.json']],
      actions: [[tl('demo.spec.tap.attribute'), 'onAttrTap → openAttribute(_:)'], [tl('demo.spec.switch.preview'), 'selectPreview(_:)']],
      transitions: [['openAttribute(_:)', 'AttributeReference']],
      branches: [['load', tl('demo.spec.unknown.name'), tl('demo.spec.back.list')], ['selectPreview', 'web', tl('demo.spec.show.web.preview')]] }),
  attrs: doc('attrs', tl('demo.spec.look.up.every.attribute.type'), '2026-10-17',
    `SafeAreaView attr_root ${tl('demo.spec.whole.screen')}|TextField search_input ${tl('demo.spec.search.attribute.name')}|Segment group_tabs ${tl('demo.spec.layout.style.behavior')}|Collection attr_list ${tl('demo.spec.attribute.list')}|Label type_label ${tl('demo.spec.type.default')}|Label platforms_label ${tl('demo.spec.supported.platforms')}|Label empty_label ${tl('demo.spec.no.matches')}`,
    { vars: [['query', 'String', '""'], ['group', 'String', '"layout"'], ['attributes', '[Attribute]', '[]'], ['isLoading', 'Bool', 'true']], handlers: [['onSearch', tl('demo.spec.filter')], ['onAttrTap', tl('demo.spec.show.components.use')]],
      methods: ['load()', 'search(_:)', 'selectGroup(_:)', 'openComponent(_:)'], repos: ['DocsRepository'], apis: [['listAttributes', 'GET', '/attributes.json']],
      actions: [[tl('demo.spec.search.attribute.name'), 'onSearch → search(_:)'], [tl('demo.spec.pick.category'), 'selectGroup(_:)'], [tl('demo.spec.tap.supported.component'), 'openComponent(_:)']],
      transitions: [['openComponent(_:)', 'ComponentDetail']],
      branches: [['search', tl('demo.spec.none'), tl('demo.spec.show.empty.label')], ['load', tl('demo.spec.loading.ssot.fails'), tl('demo.spec.show.error')], ['selectGroup', 'layout', tl('demo.spec.show.layout.attributes.only')]] }),
  anatomy: doc('anatomy', tl('demo.spec.explains.each.section.screen.spec'), '2026-09-28',
    `SafeAreaView anatomy_root ${tl('demo.spec.whole.screen')}|Label title_label ${tl('demo.spec.heading')}|Collection section_list ${tl('demo.spec.notes.per.section')}|Image diagram_image ${tl('demo.spec.structure.diagram')}|Label sample_json ${tl('demo.spec.spec.example')}`,
    { vars: [['sections', '[Section]', '[]']], handlers: [['onSectionTap', tl('demo.spec.jump.section')]],
      methods: ['load()', 'scrollTo(_:)'], repos: ['DocsRepository'], apis: [['getAnatomy', 'GET', '/spec/anatomy.json']],
      actions: [[tl('demo.spec.tap.section'), 'onSectionTap → scrollTo(_:)']],
      transitions: [[tl('demo.spec.tap.related.link'), 'AttributeReference']],
      branches: [['load', 'success', tl('demo.spec.show.diagram.example')]] }),
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
  { name: tl('demo.case.first.view.3.items'), branch: 'items.count > 0', s: 18, e: 23, steps: ['assert visible cart_list', 'assert count cart_item = 3', 'assert text total_label'] },
  { name: tl('demo.case.quantity.0.removes.row'), branch: 'changeQuantity: qty == 0', s: 23, e: 28, steps: ['input qty_input_1 "0"', 'tap qty_apply_1', 'assert count cart_item = 2'] },
  { name: tl('demo.case.empty.cart.disables.buy'), branch: 'isEmpty == true', s: 28, e: 32, steps: ['setMocks cart: empty', 'assert visible empty_label', 'assert disabled checkout_button'] },
  { name: tl('demo.case.apply.coupon.welcome10'), branch: 'applyCoupon → valid', s: 32, e: 37, steps: ['input coupon_input "WELCOME10"', 'tap coupon_apply', 'assert text discount_label'] },
  { name: tl('demo.case.expired.coupon.shows.error'), branch: 'applyCoupon → expired', s: 37, e: 45, failAt: 41, steps: ['input coupon_input "OLD2025"', 'tap coupon_apply', 'assert visible coupon_error'] },
  { name: tl('demo.case.out.stock.warning'), branch: 'item.stock == 0', s: 45, e: 50, steps: ['setMocks stock: soldOut', 'assert visible stock_warning', 'assert disabled checkout_button'] },
  { name: tl('demo.case.buy.while.signed.out.log'), branch: 'checkout → Login', s: 50, e: 55, steps: ['setMocks auth: guest', 'tap checkout_button', 'assert screen Login'] },
  { name: tl('demo.case.confirming.goes.order.complete'), branch: 'placeOrder → success', s: 55, e: 60, steps: ['tap checkout_button', 'tap confirm_button', 'assert screen OrderComplete'] },
];
/* Task lists are per session (~/.claude/tasks/<list>/), so ids repeat across lists. */
const TASKS = [
  { list: 'a0', id: 1, subject: tl('demo.task.implement.productlist.screen'), activeForm: tl('demo.task.implementing.productlist.screen'), owner: 'a5', spec: 'list', created: -1, start: -1, end: -0.5 },
  { list: 'a0', id: 2, subject: tl('demo.task.write.login.screen.spec'), activeForm: tl('demo.task.writing.login.spec'), owner: 'a3', spec: 'login', created: -1, start: 5, end: 62 },
  { list: 'a0', id: 3, subject: tl('demo.task.implement.home.layout'), activeForm: tl('demo.task.implementing.home.layout'), owner: 'a5', spec: 'home', created: -1, start: 6, end: 40.5 },
  { list: 'a0', id: 4, subject: tl('demo.task.implement.home.viewmodel'), activeForm: tl('demo.task.implementing.home.viewmodel'), owner: 'a5', spec: 'home', created: -1, start: 44, end: 76, blockedBy: 3 },
  { list: 'a0', id: 5, subject: tl('demo.task.run.cart.tests.simulator'), activeForm: tl('demo.task.running.cart.tests'), owner: 'a2', spec: 'cart', created: -1, start: 13, end: 60 },
  { list: 'a0', id: 6, subject: tl('demo.task.add.strings.strings.json'), owner: null, spec: null, created: -1, start: null, end: null },
  { list: 'a0', id: 7, subject: tl('demo.task.wire.up.home.cart'), activeForm: tl('demo.task.wiring.up.home.cart'), owner: 'a7', spec: 'home', created: 12, start: 40.5, end: null, blockedBy: 3 },
  { list: 'a0', id: 8, subject: tl('demo.task.check.drift.from.spec.jui'), activeForm: tl('demo.task.running.jui.verify'), owner: 'a5', spec: 'home', created: 12.4, start: 70, end: 74 },
  { list: 'b4', id: 1, subject: tl('demo.task.write.signup.screen.spec'), activeForm: tl('demo.task.writing.signup.spec'), owner: 'e6', spec: 'signup', created: -1, start: 5, end: 70 },
  { list: 'b4', id: 2, subject: tl('demo.task.implement.productdetail.layout'), activeForm: tl('demo.task.implementing.productdetail.layout'), owner: 'f2', spec: 'detail', created: -1, start: -1, end: 30.2 },
  { list: 'b4', id: 3, subject: tl('demo.task.implement.productdetail.viewmodel'), activeForm: tl('demo.task.implementing.productdetail.viewmodel'), owner: 'f2', spec: 'detail', created: -1, start: 36, end: 78, blockedBy: 2 },
  { list: 'b4', id: 4, subject: tl('demo.task.implement.signup.screen'), owner: null, spec: 'signup', created: -1, start: null, end: null, blockedBy: 1 },
  { list: 'b4', id: 5, subject: tl('demo.task.wire.up.productdetail.cart'), owner: null, spec: 'detail', created: 2, start: null, end: null, blockedBy: 3 },
  { list: 'd8', id: 1, subject: tl('demo.task.write.coupons.screen.spec'), owner: null, spec: 'coupons', created: -1, start: null, end: null },
  { list: '4f', id: 1, subject: tl('demo.task.fix.jui.build.s.ios'), activeForm: tl('demo.task.fixing.jui.build.s.ios'), owner: '4f', spec: null, created: -1, start: -1, end: 22 },
  { list: '4f', id: 2, subject: tl('demo.task.scaffold.jui.viz.command'), activeForm: tl('demo.task.scaffolding.jui.viz'), owner: '4f', spec: null, created: -1, start: 44, end: null },
  { list: '4f', id: 3, subject: tl('demo.task.write.tests.hook.server'), owner: null, spec: null, created: -1, start: null, end: null, blockedBy: 2 },
  { list: '7c', id: 1, subject: tl('demo.task.add.per.case.progress.output'), activeForm: tl('demo.task.implementing.progress.output'), owner: '7c', spec: null, created: -1, start: -1, end: null },
  { list: '7c', id: 2, subject: tl('demo.task.document.progress.readme'), owner: null, spec: null, created: -1, start: null, end: null, blockedBy: 1 },
  { list: 'c9', id: 1, subject: tl('demo.task.generate.html.spec.anatomy.page'), activeForm: tl('demo.task.generating.html'), owner: 'c9', spec: 'anatomy', created: -1, start: 0, end: 52 },
  { list: 'c9', id: 2, subject: tl('demo.task.add.new.attributes.component.list'), owner: null, spec: 'components', created: -1, start: null, end: null },
  { list: 'c9', id: 3, subject: tl('demo.task.fix.wording.search.page'), owner: 'c9', spec: null, created: -1, start: -1, end: -0.5 },
  { list: 'e1', id: 1, subject: tl('demo.task.write.attribute.reference.spec'), activeForm: tl('demo.task.writing.attribute.reference.spec'), owner: 'e1', spec: 'attrs', created: -1, start: 18, end: 78 },
  { list: 'e1', id: 2, subject: tl('demo.task.implement.attribute.reference'), owner: null, spec: 'attrs', created: -1, start: null, end: null, blockedBy: 1 },
];
/* The turns (requester, 10-18): one card per prompt a session received, done at Stop; 4f waits for its pip install
   (p6) while its second turn works. */
TASKS.push(
  { list: 'a0', id: 'turn-1', source: 'turn', turn: 1, subject: tl('demo.task.finish.screens.from.home.cart'), owner: 'a0', spec: null, created: -1, start: -1, end: null },
  { list: 'b4', id: 'turn-1', source: 'turn', turn: 1, subject: tl('demo.task.keep.going.sign.up.product'), owner: 'b4', spec: null, created: -1, start: -1, end: null },
  { list: '4f', id: 'turn-1', source: 'turn', turn: 1, subject: tl('demo.task.fix.jui.build.s.ios.2'), owner: '4f', spec: null, created: -1, start: -1, end: 24 },
  { list: '4f', id: 'turn-2', source: 'turn', turn: 2, subject: tl('demo.task.scaffold.jui.viz'), owner: '4f', spec: null, created: 40, start: 40, end: null, waitFrom: 42, waitTo: 44 },
  { list: 'c9', id: 'turn-1', source: 'turn', turn: 1, subject: tl('demo.task.generate.spec.anatomy.page'), owner: 'c9', spec: null, created: -1, start: -1, end: 60 },
);
const TASK_BY_KEY = Object.fromEntries(TASKS.map((x) => [`${x.list}#${x.id}`, x]));
/* Questions (AskUserQuestion) come from live sessions only: the demo script asks none. */
const QUESTIONS = [];
/* The demo's own event kinds, by code (60-log.js reads the code back with demoKindCode). */
const DEMO_KIND = { spec: tl('demo.event.spec') };
const EVENTS = [
  [0.2, 'a5', 'Read', 'docs/screens/json/home.spec.json'],
  [0.4, 'f2', 'Edit', 'docs/screens/layouts/product-detail.json'],
  [0.6, 'c9', 'Read', 'docs/screens/json/spec-anatomy.spec.json'],
  [1.4, '7c', 'Edit', 'src/reporter/progress.ts'],
  [1.0, '4f', 'Bash', 'jui build --ios-only'],
  [2.0, 'b4', 'TaskCreated', `#5 ${tl('demo.task.wire.up.productdetail.cart')}`],
  [5.0, 'a3', 'Write', 'docs/screens/json/login.spec.json'],
  [6.0, 'e6', 'PermissionRequest', 'Write docs/screens/json/signup.spec.json', 'p1'],
  [6.0, 'a5', 'Edit', 'docs/screens/layouts/home.json'],
  [8.0, 'e6', 'Write', 'docs/screens/json/signup.spec.json'],
  [9.0, 'a3', DEMO_KIND.spec, 'login.spec.json › structure'],
  [10.0, 'a2', 'MCP', 'jui-tools test_validate cart.test.json'],
  [12.0, 'a0', 'TaskCreated', `#7 ${tl('demo.task.wire.up.home.cart')}`],
  [12.2, 'e6', DEMO_KIND.spec, 'signup.spec.json › structure'],
  [12.4, 'a0', 'TaskCreated', `#8 ${tl('demo.task.check.drift.from.spec.jui')}`],
  [14.0, 'a2', 'PermissionRequest', "Bash xcodebuild test -destination 'iPhone 16'", 'p2'],
  [16.0, 'c9', 'PermissionRequest', 'Bash jsonui-doc generate html', 'p3'],
  [18.0, 'a2', 'Bash', "xcodebuild test -destination 'iPhone 16'"],
  [20.0, 'e1', 'Write', 'docs/screens/json/attribute-reference.spec.json'],
  [22.0, '4f', 'Stop', tl('demo.robot.build.complete')],
  [23.0, 'a2', 'case ✓', tl('demo.case.first.view.3.items')],
  [25.0, 'a3', DEMO_KIND.spec, 'login.spec.json › stateManagement'],
  [26.0, 'f2', 'PermissionRequest', 'Bash jui build', 'p4'],
  [28.0, 'a2', 'case ✓', tl('demo.case.quantity.0.removes.row')],
  [30.0, 'f2', 'Bash', 'jui build'],
  [30.2, 'f2', 'TaskCompleted', `#2 ${tl('demo.task.implement.productdetail.layout')}`],
  [30.4, 'e6', DEMO_KIND.spec, 'signup.spec.json › stateManagement'],
  [30.6, '7c', 'PermissionRequest', 'Bash npm test -- --progress', 'p7'],
  [26.2, 'e1', DEMO_KIND.spec, 'attribute-reference.spec.json › structure'],
  [32.0, 'a2', 'case ✓', tl('demo.case.empty.cart.disables.buy')],
  [33.0, 'a3', DEMO_KIND.spec, 'login.spec.json › dataFlow'],
  [36.0, 'f2', 'Edit', 'ProductDetailViewModel.swift'],
  [37.0, 'a2', 'case ✓', tl('demo.case.apply.coupon.welcome10')],
  [38.0, 'c9', 'PostToolUse', tl('demo.event.jsonui.doc.generate.html.allowed')],
  [40.0, 'a5', 'Bash', 'jui build'],
  [40.2, 'e6', DEMO_KIND.spec, 'signup.spec.json › dataFlow'],
  [40.4, 'e1', DEMO_KIND.spec, 'attribute-reference.spec.json › stateManagement'],
  [42.0, '4f', 'PermissionRequest', 'Bash pip install aiohttp watchdog', 'p6'],
  [40.5, 'a5', 'TaskCompleted', `#3 ${tl('demo.task.implement.home.layout')}`],
  [41.0, 'a2', 'case ✗', tl('demo.event.expired.coupon.shows.error.1st')],
  [41.2, 'a2', 'retry', tl('demo.event.retrying.expired.coupon.shows.error')],
  [43.0, 'a3', DEMO_KIND.spec, 'login.spec.json › userActions'],
  [45.0, 'a2', 'case ✓', tl('demo.event.expired.coupon.shows.error.passed')],
  [45.2, 'a5', 'PermissionRequest', 'Edit HomeViewModel.swift', 'p5'],
  [48.0, 'a5', 'Edit', 'HomeViewModel.swift'],
  [50.0, '4f', 'Edit', 'jui_cli/commands/viz_cmd.py'],
  [50.2, 'a2', 'case ✓', tl('demo.case.out.stock.warning')],
  [50.4, 'e6', DEMO_KIND.spec, 'signup.spec.json › userActions'],
  [48.2, 'e1', DEMO_KIND.spec, 'attribute-reference.spec.json › dataFlow'],
  [58.4, 'e1', DEMO_KIND.spec, 'attribute-reference.spec.json › userActions'],
  [60.6, '7c', 'Bash', 'npm test'],
  [64.4, 'e1', DEMO_KIND.spec, 'attribute-reference.spec.json › transitions'],
  [70.6, 'e1', DEMO_KIND.spec, 'attribute-reference.spec.json › branchContracts'],
  [78.0, 'e1', 'Stop', tl('demo.robot.finished.attribute.reference.spec')],
  [78.4, 'e1', 'TaskCompleted', `#1 ${tl('demo.task.write.attribute.reference.spec')}`],
  [52.0, 'c9', 'Stop', tl('demo.robot.generated.html')],
  [55.0, 'a3', DEMO_KIND.spec, 'login.spec.json › branchContracts'],
  [55.2, 'a2', 'case ✓', tl('demo.case.buy.while.signed.out.log')],
  [58.2, 'e6', DEMO_KIND.spec, 'signup.spec.json › transitions'],
  [60.0, 'a2', 'case ✓', tl('demo.case.confirming.goes.order.complete')],
  [60.2, 'a2', 'TaskCompleted', `#5 ${tl('demo.event.cart.tests.8.8.passed')}`],
  [62.0, 'a3', 'SubagentStop', tl('demo.robot.finished.login.spec')],
  [62.2, 'a3', 'TaskCompleted', `#2 ${tl('demo.task.write.login.screen.spec')}`],
  [64.2, 'e6', DEMO_KIND.spec, 'signup.spec.json › branchContracts'],
  [70.0, 'a5', 'MCP', 'jui-tools jui_verify home.spec.json'],
  [70.2, 'e6', 'SubagentStop', tl('demo.robot.finished.signup.spec')],
  [70.4, 'e6', 'TaskCompleted', `#1 ${tl('demo.task.write.signup.screen.spec')}`],
  [72.0, 'a5', 'PostToolUse', tl('demo.event.jui.verify.no.drift')],
  [74.0, 'a5', 'TaskCompleted', `#8 ${tl('demo.task.check.drift.from.spec.jui')}`],
  [74.2, 'f2', 'MCP', 'jui-tools jui_verify product-detail.spec.json'],
  [76.0, 'a5', 'TaskCompleted', `#4 ${tl('demo.task.implement.home.viewmodel')}`],
  [76.2, 'a5', 'SubagentStop', tl('demo.robot.finished.implementing.home')],
  [76.4, 'f2', 'PostToolUse', tl('demo.event.jui.verify.no.drift')],
  [78.0, 'f2', 'TaskCompleted', `#3 ${tl('demo.task.implement.productdetail.viewmodel')}`],
  [78.2, 'f2', 'SubagentStop', tl('demo.robot.finished.implementing.productdetail')],
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
  if (t < 10) statusText = tl('demo.status.idle.last.run.5.8');
  else if (t < 18) statusText = tl('demo.status.validating.test.json.test.validate');
  else if (t < 60) statusText = tl('demo.status.tests.running', { passed, n: runningIdx + 1 });
  else statusText = tl('demo.status.done.8.8.passed.1');
  return { rows, passed, runningIdx, retrying, active: t >= 18 && t < 60, statusText, file: 'tests/screens/cart.test.json', device: tl('demo.status.iphone.16.simulator') };
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
    case 'todo': return { ...base, written: BLANK, status: { kind: 'idle', text: tl('demo.status.not.started') }, note: tl('demo.status.no.spec.file.yet') };
    case 'writing': return { ...base, written: spread(share), status: { kind: 'paused', text: tl('demo.status.written.paused', { pct: pct(share) }) }, note: tl('demo.status.stopped.half.written.no.one') };
    case 'written': return { ...base, status: { kind: 'written', text: tl('demo.status.written.waiting.implementation') }, note: tl('demo.status.implementation.hasn.t.started') };
    case 'impl': return { ...base, implN: spreadImpl(T, share), implPhase: true, status: { kind: 'paused', text: tl('demo.status.impl.stopped', { pct: pct(share) }) }, note: tl('demo.status.stopped.mid.implementation.no.one') };
    case 'impl-done': return { ...base, implN: T.map((n, k) => (k === 6 ? 0 : n)), implPhase: true, status: { kind: 'impl-done', text: tl('demo.status.implemented.waiting.tests') }, note: tl('demo.status.jui.verify.no.drift.no') };
    default: return { ...base, implN: [...T], implPhase: true, status: { kind: 'done', text: tl('demo.status.implemented.tested') }, note: tl('demo.status.verified.branches', { n: T[6] }) };
  }
}
/* A define robot writing a spec section by section, watched through file changes. */
function writingSpec(t, W, who, chars) {
  const t0 = W[0][0], t1 = W[W.length - 1][1];
  const idx = W.findIndex(([a, b]) => t >= a && t < b);
  const writing = t >= t0 && t < t1;
  return {
    written: W.map(([a, b]) => frac(t, a, b)), implN: BLANK, implPhase: false, writingIdx: writing ? idx : -1, implIdx: -1, testIdx: -1, by: writing ? who : null, relatedNow: -1,
    status: t < t0 ? { kind: 'idle', text: tl('demo.status.not.started') } : writing ? { kind: 'write', text: tl('demo.status.writing', { pct: pct(frac(t, t0, t1)) }) } : { kind: 'written', text: tl('demo.status.written.waiting.implementation') },
    note: writing ? tl('demo.status.note.writing', { chars: fmtNum(Math.round(chars * frac(t, t0, t1))), section: SECTIONS[idx] }) : t < t0 ? tl('demo.status.no.spec.file.yet') : tl('demo.status.note.written', { chars: fmtNum(chars) }),
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
  if (t >= 70 && t < 76) Object.assign(login, { by: 'a3', status: { kind: 'verify', text: tl('demo.status.running.doc.validate.spec') } });
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
    status: t < 6 ? { kind: 'impl', text: tl('demo.status.reading.spec') } : t < 70 ? { kind: 'impl', text: tl('demo.status.implementing', { pct: pct(sumImpl(hd) / sumImpl(H)) }) } : t < 76 ? { kind: 'verify', text: tl('demo.status.running.jui.verify') } : { kind: 'impl-done', text: tl('demo.status.implemented.waiting.tests') },
    by: t < 76 ? 'a5' : null, relatedNow: hIdx === 1 ? 0 : hIdx >= 2 ? 1 : -1,
    note: `jui verify: ${t < 70 ? tl('demo.status.verify.matching') : t < 72 ? tl('demo.status.verify.checking') : tl('demo.status.verify.nodrift')}`,
  });

  // f2 (session b4) implements ProductDetail the same way.
  const D = SPECS[SPEC_INDEX.detail].totals;
  const dd = [0, Math.min(D[1], 4 + Math.floor((D[1] - 4) * frac(t, 0, 30))), Math.floor(D[2] * frac(t, 36, 56)), Math.floor(D[3] * frac(t, 36, 70)), Math.floor(D[4] * frac(t, 48, 72)), Math.floor(D[5] * frac(t, 60, 74)), 0];
  let dIdx = -1;
  if (t < 30) dIdx = 1; else if (t >= 36 && t < 50) dIdx = 2; else if (t >= 50 && t < 62) dIdx = 3; else if (t >= 62 && t < 70) dIdx = 4; else if (t >= 70 && t < 74) dIdx = 5;
  const dPct = tl('demo.status.implementing', { pct: pct(sumImpl(dd) / sumImpl(D)) });
  put('detail', {
    written: FULL, implN: dd, implPhase: true, writingIdx: -1, implIdx: dIdx, testIdx: -1,
    status: t < 30 ? { kind: 'impl', text: dPct } : t < 36 ? { kind: 'impl', text: tl('demo.status.running.jui.build') } : t < 74 ? { kind: 'impl', text: dPct } : t < 78 ? { kind: 'verify', text: tl('demo.status.running.jui.verify') } : { kind: 'impl-done', text: tl('demo.status.implemented.waiting.tests') },
    by: t < 78 ? 'f2' : null, relatedNow: dIdx === 1 || (t >= 30 && t < 36) ? 0 : dIdx >= 2 ? 1 : -1,
    note: `jui verify: ${t < 74 ? tl('demo.status.verify.notrun') : t < 76 ? tl('demo.status.verify.checking') : tl('demo.status.verify.nodrift')}`,
  });

  // a2 runs the Cart tests on the simulator; each passing case covers one branchContract.
  const C = SPECS[SPEC_INDEX.cart].totals;
  const cov = t < 18 ? 5 : tests.passed;
  put('cart', {
    written: FULL, implN: [...C.slice(0, 6), cov], implPhase: true, writingIdx: -1, implIdx: -1, testIdx: tests.active ? 6 : -1,
    status: t < 10 ? { kind: 'impl-done', text: tl('demo.status.implemented.waiting.tests') } : t < 18 ? { kind: 'test', text: tl('demo.status.validating.test.json') } : t < 60 ? { kind: 'test', text: tl('demo.status.testing', { passed: tests.passed }) } : { kind: 'done', text: tl('demo.status.implemented.tested') },
    by: t >= 10 && t < 60 ? 'a2' : null, relatedNow: t >= 10 && t < 60 ? 2 : -1,
    note: tl('demo.status.cart.note', { cov, last: t < 18 ? tl('demo.status.cart.note.last') : '' }),
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
  const decision = behavior === 'deny' ? { behavior: 'deny', message: reason || tl('demo.perm.denied.agent.view') } : { behavior: 'allow' };
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
  // a subagent called (10-20): the whistle for launchSec (robots.py LAUNCH_WHISTLE_MS) from each [t, robot, how]:
  // a0 calls one in the foreground at 20 (then waits for its report), b4 at 6, a0 one in the background at 76
  launch: [[6, 'b4', 'fg'], [20, 'a0', 'fg'], [76, 'a0', 'bg']], launchSec: 2.5,
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
const demoLaunch = (id, t) => DEMO_BEATS.launch.some(([at, who]) => who === id && t >= at && t < at + DEMO_BEATS.launchSec);
const demoHeavy = (id, t) => (id === DEMO_BEATS.heavy[2] && t >= DEMO_BEATS.heavy[0] && t < DEMO_BEATS.heavy[1] ? ['tokens'] : []);
function robotCondition(id) {
  const t = latestModel ? latestModel.t : 0;
  return { tired: demoTired(id), hours: (vizNow() - demoDayMs()) / 3600000 - DEMO_BEATS.tired.since,
    heavy: demoHeavy(id, t).length ? { reasons: ['tokens'], tokensPerMin: 3200 } : null };
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
    const item = { abs: simT, who: p.who, kind: behavior === 'deny' ? tl('demo.perm.denied') : tl('demo.perm.allowed'), what: `${p.tool} ${permSummary(p)}${behavior === 'always' ? tl('demo.perm.always.note', { rule: p.rule }) : ''}${reason ? tl('demo.perm.reason.note', { reason }) : ''}`, seq: ++logSeq, perm: id, decision: behavior, reason };
    tickerItems.unshift(item); logItems.unshift(item);
    showToast(tl('demo.perm.toast', { who: p.who, tool: p.tool, how: behavior === 'deny' ? tl('demo.perm.toast.denied') : behavior === 'always' ? tl('demo.perm.toast.always') : tl('demo.perm.toast.allowed') }));
  },
  specDiff() { return Promise.resolve({ ok: false, error: 'demo' }); },   // the demo has no worktrees (50-spec-diff.js)
  specDiffList() { return Promise.resolve({ ok: false, error: 'demo' }); },
  history() { return Promise.resolve({ ok: false, error: 'demo' }); },   // the demo has no transcripts
  historyImage() { return Promise.resolve({ ok: false, status: 0, error: 'demo' }); },
  historyFile() { return Promise.resolve({ ok: false, status: 0, error: 'demo' }); },
  attachImage() { return Promise.resolve({ ok: false, status: 0, error: 'demo' }); },
  revealFile() { return Promise.resolve({ ok: false, status: 0, error: tl('demo.perm.not.opened.demo') }); },
  attachFile() { return Promise.resolve({ ok: false, status: 0, error: 'demo' }); },
  attachRemove() {},
  denial() { return Promise.resolve({ ok: false, status: 0, error: 'demo' }); },
  notifyPresence() { return Promise.resolve(); },
  callCommand() { return Promise.resolve({ ok: false, why: tl('demo.perm.not.available.demo.there.no') }); },
  localModels() { return Promise.resolve({ ok: false }); },
  setWeather() { return Promise.resolve({ ok: false, error: 'demo' }); },   // the demo asks nobody about the weather
  // the server room (ticket 2026-10-20-jui-viz-server-room): shop-app/'s door reads a made-up, generic layout (no real
  // service's values, requester 10-20), after a moment so the keypad's * are seen
  infraDocs(project, seq) { return new Promise((r) => setTimeout(() => r(project === 'shop' ? { ...demoInfra(), seq } : { ok: false, seq, reason: 'no_infra', message: tl('demo.perm.this.demo.room.has.no'), short: tl('demo.perm.no.docs.infra') }), 1200)); },
  infraIcon() { return Promise.resolve(null); },
  infraCost() { return Promise.resolve({ ok: false, reason: 'demo', message: tl('demo.cost.none') }); },
};
/* The demo's server room: a made-up web shop on one cloud, a CDN in front, a card payment service outside, two
   environments; the IAM role and the alarm are folded until asked for. */
function demoInfra() {
  const both = ['production', 'staging'], prod = ['production'];
  const g = (id, label, kind, extra = {}) => ({ id, label, kind, environments: both, providerResolved: extra.provider || '', ...extra });
  const n = (id, label, category, group, provider, extra = {}) => ({ id, label, category, group, count: 1, providerResolved: provider, managed_by: 'iac', fold: false, environments: both, ...extra });
  const e = (from, to, protocol, crossProvider = false, environments = both) => ({ from, to, protocol, direction: 'out', environments, crossProvider });
  return {
    ok: true, version: 0, dir: 'docs/infra', files: ['shop.json', 'shop-staging.json'], readMs: 3, icons: {}, problems: [],
    environments: [{ id: 'production', label: 'production', kind: 'production' }, { id: 'staging', label: 'staging', kind: 'staging' }],
    groups: [
      g('shop', tl('demo.infra.shop.all'), 'logical'),
      g('cloud', tl('demo.infra.cloud.account'), 'account', { provider: 'aws', parent: 'shop' }),
      g('vpc', 'VPC', 'network', { provider: 'aws', parent: 'cloud' }),
      g('pub', tl('demo.infra.public.subnet'), 'subnet', { provider: 'aws', parent: 'vpc', visibility: 'public' }),
      g('app', tl('demo.infra.app.subnet'), 'subnet', { provider: 'aws', parent: 'vpc', visibility: 'private' }),
      g('data', tl('demo.infra.data.subnet'), 'subnet', { provider: 'aws', parent: 'vpc', visibility: 'private' }),
      g('edge', tl('demo.infra.cdn.account'), 'account', { provider: 'cloudflare', parent: 'shop' }),
    ],
    nodes: [
      n('browser', tl('demo.infra.browser'), 'client', undefined, '', { group: undefined }),
      n('cdn', 'CDN', 'edge.cdn', 'edge', 'cloudflare'),
      n('dns', 'DNS', 'edge.dns', 'edge', 'cloudflare'),
      n('lb', tl('demo.infra.load.balancer'), 'load_balancer', 'pub', 'aws'),
      n('web', tl('demo.infra.web.app'), 'compute.container', 'app', 'aws', { count: 3, service: 'ecs.fargate', spec: [{ key: 'cpu', value: '512' }, { key: 'memory', value: '1024' }] }),
      n('worker', tl('demo.infra.order.worker'), 'compute.container', 'app', 'aws'),
      n('queue', tl('demo.infra.order.queue'), 'queue', 'app', 'aws', { service: 'sqs' }),
      n('db', tl('demo.infra.order.db'), 'database.relational', 'data', 'aws', { service: 'rds.postgres', engine: 'postgres 16', spec: [{ key: 'instance_class', value: 'db.r6g.large' }, { key: 'storage_gb', value: '200' }, { key: 'multi_az', value: 'true' }] }),
      n('replica', tl('demo.infra.read.replica'), 'database.relational', 'data', 'aws', { environments: prod }),
      n('cache', tl('demo.infra.session.cache'), 'cache', 'data', 'aws', { service: 'elasticache', spec: [{ key: 'node_type', value: 'cache.t4g.small' }] }),
      n('images', tl('demo.infra.product.images'), 'storage.object', 'cloud', 'aws'),
      n('role', tl('demo.infra.app.iam.role'), 'security.iam', 'cloud', 'aws', { fold: true }),
      n('alarm', tl('demo.infra.5xx.alarm'), 'monitoring.alarm', 'cloud', 'aws', { fold: true }),
      n('pay', tl('demo.infra.card.payments.external'), 'external.saas', undefined, '', { external: true, group: undefined }),
    ],
    edges: [
      e('browser', 'dns', 'dns'), e('browser', 'cdn', 'https'), e('cdn', 'lb', 'https', true), e('cdn', 'images', 'https', true),
      e('lb', 'web', 'http'), e('web', 'cache', 'redis'), e('web', 'db', 'postgres'), e('web', 'queue', 'sqs'),
      e('worker', 'queue', 'sqs'), e('worker', 'db', 'postgres'), e('db', 'replica', 'postgres', false, prod),
      e('worker', 'pay', 'https'), e('worker', 'cache', 'redis', false, ['staging']), e('alarm', 'lb', 'metrics'), e('role', 'web', 'iam'),
    ],
    // what the shop does, step by step (59-sr-flows.js): a person's order with a branch, and the worker's schedule
    flows: [
      { id: 'order', label: tl('demo.flow.order'), start: 'browser', trigger: 'user', environments: both, steps: [
        { from: 'browser', to: 'cdn', action: 'request', label: 'POST /orders' }, { from: 'cdn', to: 'lb', action: 'request' },
        { from: 'lb', to: 'web', action: 'request' },
        { branch: { label: tl('demo.flow.order.cached'), default: 'hit', choices: [
          { id: 'hit', label: tl('demo.flow.order.hit'), steps: [{ from: 'web', to: 'cache', action: 'read' }, { from: 'cache', to: 'web', action: 'response' }] },
          { id: 'miss', label: tl('demo.flow.order.miss'), steps: [{ from: 'web', to: 'db', action: 'read' }, { from: 'db', to: 'web', action: 'response' }] }] } },
        { from: 'web', to: 'db', action: 'write', label: tl('demo.flow.order.save') },
        { from: 'db', to: 'web', action: 'response' },
        { from: 'web', to: 'queue', action: 'enqueue', async: true, label: tl('demo.flow.order.pay') },
        { from: 'web', to: 'lb', action: 'response' }, { from: 'lb', to: 'cdn', action: 'response' },
        { from: 'cdn', to: 'browser', action: 'response', label: tl('demo.flow.order.taken') }] },
      { id: 'pay', label: tl('demo.flow.pay'), start: 'worker', trigger: 'schedule', schedule: 'rate(1 minute)', environments: both, steps: [
        { from: 'worker', to: 'queue', action: 'dequeue' }, { from: 'queue', to: 'worker', action: 'response' },
        { from: 'worker', to: 'pay', action: 'request', label: tl('demo.flow.pay.card') }, { from: 'pay', to: 'worker', action: 'response' },
        { from: 'worker', to: 'db', action: 'write', label: tl('demo.flow.pay.done') }] },
    ],
  };
}
const robotRuns = () => [];   // the demo's one test run is shown by the card's own a2 row

/* ---------- robot states (kept even without WebGL so the panels still run) ---------- */
const robotState = Object.fromEntries(ROBOT_DEFS.map((d) => [d.id, { state: 'idle', act: '' }]));
function updateRobotStates(simT, t, perms) {
  for (const d of ROBOT_DEFS) {
    if (d.walk) {
      const w = walkAt(simT);
      const started = t >= TASK_BY_KEY['a0#7'].start;
      robotState[d.id] = { state: w.moving ? 'carry' : 'idle', act: w.moving ? (started ? tl('demo.robot.carrying.papers.7.home.cart') : tl('demo.robot.carrying.research.notes.7.waits')) : tl('demo.robot.handing.over.papers'), walk: w };
      continue;
    }
    let st = planAt(d.plan, t);
    // While a permission prompt is open the robot waits; an answer from the view lets it go on before the script would.
    const p = perms.find((x) => x.who === d.id && t < x.end && x.status !== 'terminal');
    if (p && p.status === 'pending') st = { state: 'waiting', act: tl('demo.robot.waiting.permission', { tool: p.tool, what: permSummary(p) }) };
    else if (p && p.status === 'deny') st = { state: 'reading', act: tl('demo.robot.denied.so.thinking.another.way') };
    else if (p) { const next = planAt(d.plan, p.end); st = { state: next.state, act: tl('demo.robot.act.allowed', { act: next.act, how: p.status === 'rule' ? tl('demo.robot.allowed.rule') : tl('demo.robot.allowed.view') }) }; }
    robotState[d.id] = st;
  }
}

/* ---------- トーク (2.3.6): the demo's stand-in for the server's talk frames (TALK_CONTRACT.md) ----------
   The talks themselves are 31-talk-demo-data.js (TALK_DEMO: generated frames, data only; it comes after this file, so it
   is read only when the first request comes). talkStandIn answers the page's talk.* requests from them the way the
   server does: talk.open → the robot's list, talk.get → a page of messages (before / limit), talk.seen → the unread
   recounted (a conv op, and talk.badges when a total changed). The data's script (a new message at 20 s, a read at 30 s,
   a removal at 45 s) plays on the page's clock; ?talkhold=1 holds it for the e2e, which plays it with talkDemo.play(t).
   Times move by (now − base). tests/test_viz_talk_ui_frames.py runs this block under node and validates every frame. */
/* talk-demo:begin */
function talkStandIn(data, now) {
  const shift = now - data.base;
  const TIMES = ['at', 'deliveredAt', 'readAt', 'lastAt', 'goneAt', 'removeAt'];
  const moved = (v) => {   // a deep copy with every time moved to the page's clock
    if (Array.isArray(v)) return v.map(moved);
    if (!v || typeof v !== 'object') return v;
    const o = {};
    for (const [k, x] of Object.entries(v)) o[k] = TIMES.includes(k) && Number.isFinite(x) ? x + shift : moved(x);
    return o;
  };
  const lists = {}, msgs = {}, seen = {};
  for (const [owner, f] of Object.entries(data.lists)) lists[owner] = moved(f.items);
  for (const [key, f] of Object.entries(data.messages)) msgs[key] = moved(f.items);
  const ins = (owner, convId) => (msgs[`${owner} ${convId}`] || []).filter((m) => m.dir === 'in');
  // "seen" up to where the data's unread count says: the newest `unread` messages in are not seen yet
  for (const [owner, items] of Object.entries(lists)) for (const c of items) {
    const list = ins(owner, c.id).sort((a, b) => a.at - b.at);
    const k = list.length - c.unread - 1;
    seen[`${owner} ${c.id}`] = k >= 0 ? list[k].at : 0;
  }
  const unread = (owner, convId) => ins(owner, convId).filter((m) => m.at > (seen[`${owner} ${convId}`] || 0)).length;
  const row = (owner, convId) => (lists[owner] || []).find((c) => c.id === convId);
  const recount = (owner, convId) => { const c = row(owner, convId); if (c) c.unread = unread(owner, convId); return c; };
  function badges() {
    const counts = {};
    for (const [owner, items] of Object.entries(lists)) { const n = items.reduce((a, c) => a + c.unread, 0); if (n) counts[owner] = n; }
    return { type: 'talk.badges', counts };
  }
  const ack = (reqId, error) => ({ type: 'ack', reqId, ok: false, error });
  function handle(f) {
    if (f.type === 'talk.open') {
      const items = (lists[f.agentId] || []).slice().sort((a, b) => b.lastAt - a.lastAt);
      return [{ type: 'talk.list', reqId: f.reqId, agentId: f.agentId, items: items.slice(0, 200), more: items.length > 200 }];
    }
    if (f.type === 'talk.close') return [];
    const all = msgs[`${f.agentId} ${f.convId}`];
    if (!all || !row(f.agentId, f.convId)) return [ack(f.reqId, 'no such conversation')];
    if (f.type === 'talk.get') {
      let end = all.length;
      if (f.before !== undefined) { end = all.findIndex((m) => m.id === f.before); if (end < 0) return [ack(f.reqId, 'no such message')]; }
      const start = Math.max(0, end - (f.limit || 100));
      return [{ type: 'talk.messages', reqId: f.reqId, agentId: f.agentId, convId: f.convId, items: all.slice(start, end), more: start > 0 }];
    }
    if (f.type === 'talk.seen') {
      const before = JSON.stringify(badges()), k = `${f.agentId} ${f.convId}`;
      seen[k] = Math.max(seen[k] || 0, f.upTo);
      const out = [{ type: 'talk.update', agentId: f.agentId, ops: [{ op: 'conv', conv: recount(f.agentId, f.convId) }] }];
      const after = badges();
      if (JSON.stringify(after) !== before) out.push(after);
      return out;
    }
    return [ack(f.reqId, 'unknown request')];
  }
  /* One frame of the data's script, applied to the state; what goes out is recounted from the state (a seen before it
     counts), so the badge and the rows never disagree with what the page told the stand-in. */
  function apply(frame) {
    const f = moved(frame);
    if (f.type === 'talk.badges') return [badges()];
    if (f.type !== 'talk.update') return [];
    const owner = f.agentId, ops = [];
    for (const op of f.ops) {
      if (op.op === 'message') {
        const key = `${owner} ${op.convId}`, list = msgs[key] || (msgs[key] = []);
        const k = list.findIndex((m) => m.id === op.message.id);
        if (k >= 0) list[k] = op.message; else { list.push(op.message); list.sort((a, b) => a.at - b.at); }
        ops.push(op);
      } else if (op.op === 'conv') {
        const items = lists[owner] || (lists[owner] = []), k = items.findIndex((c) => c.id === op.conv.id);
        if (k >= 0) items[k] = op.conv; else items.push(op.conv);
        ops.push({ op: 'conv', conv: recount(owner, op.conv.id) });
      } else if (op.op === 'remove') {
        lists[owner] = (lists[owner] || []).filter((c) => c.id !== op.convId);
        delete msgs[`${owner} ${op.convId}`];
        ops.push(op);
      }
    }
    return ops.length ? [{ type: 'talk.update', agentId: owner, ops }] : [];
  }
  return { handle, badges, apply, script: data.script };
}
/* talk-demo:end */
const TALK_SOCK = { open: null, stand: null, played: new Set() };
const talkStand = () => TALK_SOCK.stand || (TALK_SOCK.stand = talkStandIn(TALK_DEMO, Date.now()));
/* Frames reach the page a moment later, as from the socket; an update only for the robot this "socket" has open. */
function talkDemoDeliver(frames) {
  for (const f of frames) {
    if (f.type === 'ack') continue;
    if (f.type === 'talk.update' && f.agentId !== TALK_SOCK.open) continue;
    setTimeout(() => talkReceive(f), 30);
  }
}
/* The script's frames due by t seconds (each once). */
function talkDemoPlay(t) {
  const S = talkStand();
  S.script.forEach((x, k) => { if (x.t <= t && !TALK_SOCK.played.has(k)) { TALK_SOCK.played.add(k); talkDemoDeliver(S.apply(x.frame)); } });
}
Object.assign(SOURCE, {
  talkAgentId: (label) => (DEF[label] ? label : null),   // the demo's talks name the robots by their labels
  talkLabel: (agentId) => (agentId && DEF[agentId] ? agentId : null),
  /* One request, already checked against the contract (58-talk.js talkFrame). Resolves { ok, data } / { ok: false, error }. */
  talkSend(frame) {
    if (frame.type === 'talk.open') TALK_SOCK.open = frame.agentId;
    if (frame.type === 'talk.close') TALK_SOCK.open = null;
    const out = talkStand().handle(frame);
    const fail = out.find((f) => f.type === 'ack' && f.reqId === frame.reqId);
    const answer = out.find((f) => f.type === 'talk.messages' && f.reqId === frame.reqId);
    talkDemoDeliver(out.filter((f) => f !== answer));
    return new Promise((resolve) => setTimeout(() => resolve(fail ? { ok: false, error: fail.error } : { ok: true, data: answer || null }), 30));
  },
  /* The e2e's hand on the script: play what is due by t seconds. */
  talkDemo: { play: (t) => talkDemoPlay(t) },
});
setTimeout(() => {
  talkDemoDeliver([talkStand().badges()]);   // as the server sends it right after auth
  if (new URLSearchParams(location.search).get('talkhold') !== '1') {
    for (const t of [...new Set(talkStand().script.map((x) => x.t))]) setTimeout(() => talkDemoPlay(t), t * 1000);
  }
}, 0);
