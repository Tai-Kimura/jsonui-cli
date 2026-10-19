// The talk view's demo data: frames as jui_cli/viz/talk_contract.json says (data only, no code). Read by the demo
// source in place of the server's talk.* frames. Checked by tests/test_viz_talk_demo_data.py.
// eslint-disable-next-line no-unused-vars
const TALK_DEMO = {
 "about": "The talk view's demo data (frames as talk_contract.json says), for the demo page only. Times are ms around base; the page moves them by its own clock (now - base). script: frames that arrive t seconds into the demo.",
 "contractVersion": 2,
 "base": 1792300000000,
 "badges": {
  "type": "talk.badges",
  "counts": {
   "a0": 2
  }
 },
 "lists": {
  "a0": {
   "type": "talk.list",
   "agentId": "a0",
   "items": [
    {
     "id": "t-e7be89fd2788347b",
     "owner": "a0",
     "peer": {
      "key": "4f",
      "agentId": "4f",
      "sessionId": "4f2b0000-0000-4000-8000-00000000004f",
      "name": "jsonui-agents-for-claude-4f-library-orchestrator-for-the-2.3.7-train",
      "kind": "session",
      "alive": true,
      "goneAt": null,
      "removeAt": null
     },
     "lastAt": 1792299520000,
     "preview": "2.3.7 の列車の範囲を決めました。トークの画面が入ります。",
     "lastDir": "in",
     "unread": 1,
     "count": 1
    },
    {
     "id": "t-70adb9b17963bc5a",
     "owner": "a0",
     "peer": {
      "key": "b4",
      "agentId": "b4",
      "sessionId": "b47e0000-0000-4000-8000-0000000000b4",
      "name": "shop-app-signup",
      "kind": "session",
      "alive": true,
      "goneAt": null,
      "removeAt": null
     },
     "lastAt": 1792299400000,
     "preview": "ありがとう。住所の自動入力は次の列車で大丈夫です。",
     "lastDir": "out",
     "unread": 1,
     "count": 4
    },
    {
     "id": "t-56ee3add5d59df3a",
     "owner": "a0",
     "peer": {
      "key": "x:cloud-reviewer",
      "agentId": null,
      "sessionId": null,
      "name": "cloud-reviewer",
      "kind": "external",
      "alive": false,
      "goneAt": 1792298800000,
      "removeAt": 1792302400000
     },
     "lastAt": 1792298800000,
     "preview": "レビューをお願いします（クラウドの相手へ）",
     "lastDir": "out",
     "unread": 0,
     "count": 1
    },
    {
     "id": "t-68f5487e3df0ef59",
     "owner": "a0",
     "peer": {
      "key": "a3",
      "agentId": "a3",
      "sessionId": "a07c0000-0000-4000-8000-0000000000a0",
      "name": "サブエージェント a3（jsonui-define）",
      "kind": "subagent",
      "alive": true,
      "goneAt": null,
      "removeAt": null
     },
     "lastAt": 1792298500000,
     "preview": "足しました。doc_validate_spec は緑です。",
     "lastDir": "in",
     "unread": 0,
     "count": 2
    },
    {
     "id": "t-d74ea5e94db195e1",
     "owner": "a0",
     "peer": {
      "key": "d8",
      "agentId": "d8",
      "sessionId": "d8a50000-0000-4000-8000-0000000000d8",
      "name": "shop-app-payment",
      "kind": "session",
      "alive": false,
      "goneAt": 1792299700000,
      "removeAt": 1792303300000
     },
     "lastAt": 1792297120000,
     "preview": "シミュレーターを待っています。空いたら流します。",
     "lastDir": "in",
     "unread": 0,
     "count": 2
    }
   ],
   "more": false
  },
  "b4": {
   "type": "talk.list",
   "agentId": "b4",
   "items": [
    {
     "id": "t-70adb9b17963bc5a",
     "owner": "b4",
     "peer": {
      "key": "a0",
      "agentId": "a0",
      "sessionId": "a07c0000-0000-4000-8000-0000000000a0",
      "name": "shop-app-main",
      "kind": "session",
      "alive": true,
      "goneAt": null,
      "removeAt": null
     },
     "lastAt": 1792299400000,
     "preview": "ありがとう。住所の自動入力は次の列車で大丈夫です。",
     "lastDir": "in",
     "unread": 0,
     "count": 4
    }
   ],
   "more": false
  },
  "a3": {
   "type": "talk.list",
   "agentId": "a3",
   "items": [
    {
     "id": "t-68f5487e3df0ef59",
     "owner": "a3",
     "peer": {
      "key": "a0",
      "agentId": "a0",
      "sessionId": "a07c0000-0000-4000-8000-0000000000a0",
      "name": "shop-app-main",
      "kind": "session",
      "alive": true,
      "goneAt": null,
      "removeAt": null
     },
     "lastAt": 1792298500000,
     "preview": "足しました。doc_validate_spec は緑です。",
     "lastDir": "out",
     "unread": 0,
     "count": 2
    }
   ],
   "more": false
  },
  "4f": {
   "type": "talk.list",
   "agentId": "4f",
   "items": [
    {
     "id": "t-e7be89fd2788347b",
     "owner": "4f",
     "peer": {
      "key": "a0",
      "agentId": "a0",
      "sessionId": "a07c0000-0000-4000-8000-0000000000a0",
      "name": "shop-app-main",
      "kind": "session",
      "alive": true,
      "goneAt": null,
      "removeAt": null
     },
     "lastAt": 1792299520000,
     "preview": "2.3.7 の列車の範囲を決めました。トークの画面が入ります。",
     "lastDir": "out",
     "unread": 0,
     "count": 1
    }
   ],
   "more": false
  },
  "d8": {
   "type": "talk.list",
   "agentId": "d8",
   "items": [
    {
     "id": "t-d74ea5e94db195e1",
     "owner": "d8",
     "peer": {
      "key": "a0",
      "agentId": "a0",
      "sessionId": "a07c0000-0000-4000-8000-0000000000a0",
      "name": "shop-app-main",
      "kind": "session",
      "alive": true,
      "goneAt": null,
      "removeAt": null
     },
     "lastAt": 1792297120000,
     "preview": "シミュレーターを待っています。空いたら流します。",
     "lastDir": "out",
     "unread": 0,
     "count": 2
    }
   ],
   "more": false
  }
 },
 "messages": {
  "a0 t-70adb9b17963bc5a": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "a0",
   "convId": "t-70adb9b17963bc5a",
   "items": [
    {
     "id": "m-demo-0001-0000-4000-8000-000000000000",
     "msgId": "demo-0001-0000-4000-8000-000000000000",
     "convId": "t-70adb9b17963bc5a",
     "dir": "out",
     "fromName": "shop-app-main",
     "toName": "shop-app-signup",
     "at": 1792297480000,
     "deliveredAt": 1792297480800,
     "readAt": 1792297481600,
     "state": "read",
     "text": "会員登録の画面、進み具合はどう？",
     "cut": false,
     "summary": "会員登録の進み具合",
     "seen": "both",
     "via": "session",
     "merged": false
    },
    {
     "id": "m-demo-0002-0000-4000-8000-000000000000",
     "msgId": "demo-0002-0000-4000-8000-000000000000",
     "convId": "t-70adb9b17963bc5a",
     "dir": "in",
     "fromName": "shop-app-signup",
     "toName": "shop-app-main",
     "at": 1792297600000,
     "deliveredAt": 1792297600800,
     "readAt": 1792297601600,
     "state": "read",
     "text": "いま入力の検証を書いています。30 分ほどで出せます。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "session",
     "merged": false
    },
    {
     "id": "m-demo-0003-0000-4000-8000-000000000000",
     "msgId": "demo-0003-0000-4000-8000-000000000000",
     "convId": "t-70adb9b17963bc5a",
     "dir": "in",
     "fromName": "shop-app-signup",
     "toName": "shop-app-main",
     "at": 1792299280000,
     "deliveredAt": 1792299280800,
     "readAt": 1792299281600,
     "state": "read",
     "text": "会員登録の画面を仕上げました。確認してほしい点は次のとおりです。\n\n1. **メールアドレス**の入力欄は、確認用の欄と一致しないとき `送信` を押せないようにしました。\n2. パスワードは 8 文字以上、英字と数字を含むこと。弱いときは赤い文で理由を出します。\n3. 利用規約のリンクは別画面で開きます（戻ると入力は残ります）。\n\nテスト: `jsonui-test run tests/screens/signup` で 14 件すべて通りました。\niOS と Android のスクリーンショットは docs/screens/signup/ に置いてあります。\n<script>alert(1)</script> のような文字列も、そのまま文字として出ること（escape の見本）。\n残り: 住所の自動入力は次の列車で。",
     "cut": false,
     "summary": "会員登録の画面を仕上げた",
     "seen": "both",
     "via": "session",
     "merged": false
    },
    {
     "id": "m-demo-0004-0000-4000-8000-000000000000",
     "msgId": "demo-0004-0000-4000-8000-000000000000",
     "convId": "t-70adb9b17963bc5a",
     "dir": "out",
     "fromName": "shop-app-main",
     "toName": "shop-app-signup",
     "at": 1792299400000,
     "deliveredAt": 1792299400800,
     "readAt": null,
     "state": "delivered",
     "text": "ありがとう。住所の自動入力は次の列車で大丈夫です。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "session",
     "merged": false
    }
   ],
   "more": false
  },
  "a0 t-68f5487e3df0ef59": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "a0",
   "convId": "t-68f5487e3df0ef59",
   "items": [
    {
     "id": "u-toolu_demo_0005",
     "msgId": null,
     "convId": "t-68f5487e3df0ef59",
     "dir": "out",
     "fromName": "shop-app-main",
     "toName": "サブエージェント a3（jsonui-define）",
     "at": 1792298200000,
     "deliveredAt": 1792298200800,
     "readAt": 1792298201600,
     "state": "read",
     "text": "signup.spec.json の項目を 3 つ足して、検証を通してください。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "subagent",
     "merged": false
    },
    {
     "id": "u-toolu_demo_0006",
     "msgId": null,
     "convId": "t-68f5487e3df0ef59",
     "dir": "in",
     "fromName": "サブエージェント a3（jsonui-define）",
     "toName": "shop-app-main",
     "at": 1792298500000,
     "deliveredAt": 1792298500800,
     "readAt": 1792298501600,
     "state": "read",
     "text": "足しました。doc_validate_spec は緑です。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "parent",
     "merged": false
    }
   ],
   "more": false
  },
  "a0 t-56ee3add5d59df3a": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "a0",
   "convId": "t-56ee3add5d59df3a",
   "items": [
    {
     "id": "u-toolu_demo_0007",
     "msgId": null,
     "convId": "t-56ee3add5d59df3a",
     "dir": "out",
     "fromName": "shop-app-main",
     "toName": "cloud-reviewer",
     "at": 1792298800000,
     "deliveredAt": null,
     "readAt": null,
     "state": "undelivered",
     "text": "レビューをお願いします（クラウドの相手へ）",
     "cut": false,
     "summary": null,
     "seen": "sender",
     "via": "external",
     "merged": false
    }
   ],
   "more": false
  },
  "a0 t-e7be89fd2788347b": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "a0",
   "convId": "t-e7be89fd2788347b",
   "items": [
    {
     "id": "m-demo-0008-0000-4000-8000-000000000000",
     "msgId": "demo-0008-0000-4000-8000-000000000000",
     "convId": "t-e7be89fd2788347b",
     "dir": "in",
     "fromName": "jsonui-agents-for-claude-4f-library-orchestrator-for-the-2.3.7-train",
     "toName": "shop-app-main",
     "at": 1792299520000,
     "deliveredAt": 1792299520800,
     "readAt": 1792299521600,
     "state": "read",
     "text": "2.3.7 の列車の範囲を決めました。トークの画面が入ります。",
     "cut": false,
     "summary": "2.3.7 の範囲",
     "seen": "both",
     "via": "session",
     "merged": false
    }
   ],
   "more": false
  },
  "a0 t-d74ea5e94db195e1": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "a0",
   "convId": "t-d74ea5e94db195e1",
   "items": [
    {
     "id": "m-demo-0009-0000-4000-8000-000000000000",
     "msgId": "demo-0009-0000-4000-8000-000000000000",
     "convId": "t-d74ea5e94db195e1",
     "dir": "out",
     "fromName": "shop-app-main",
     "toName": "shop-app-payment",
     "at": 1792297000000,
     "deliveredAt": 1792297000800,
     "readAt": 1792297001600,
     "state": "read",
     "text": "決済の画面のテスト、止まっていますか？",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "session",
     "merged": false
    },
    {
     "id": "m-demo-0010-0000-4000-8000-000000000000",
     "msgId": "demo-0010-0000-4000-8000-000000000000",
     "convId": "t-d74ea5e94db195e1",
     "dir": "in",
     "fromName": "shop-app-payment",
     "toName": "shop-app-main",
     "at": 1792297120000,
     "deliveredAt": 1792297120800,
     "readAt": 1792297121600,
     "state": "read",
     "text": "シミュレーターを待っています。空いたら流します。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "session",
     "merged": false
    }
   ],
   "more": false
  },
  "b4 t-70adb9b17963bc5a": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "b4",
   "convId": "t-70adb9b17963bc5a",
   "items": [
    {
     "id": "m-demo-0001-0000-4000-8000-000000000000",
     "msgId": "demo-0001-0000-4000-8000-000000000000",
     "convId": "t-70adb9b17963bc5a",
     "dir": "in",
     "fromName": "shop-app-main",
     "toName": "shop-app-signup",
     "at": 1792297480000,
     "deliveredAt": 1792297480800,
     "readAt": 1792297481600,
     "state": "read",
     "text": "会員登録の画面、進み具合はどう？",
     "cut": false,
     "summary": "会員登録の進み具合",
     "seen": "both",
     "via": "session",
     "merged": false
    },
    {
     "id": "m-demo-0002-0000-4000-8000-000000000000",
     "msgId": "demo-0002-0000-4000-8000-000000000000",
     "convId": "t-70adb9b17963bc5a",
     "dir": "out",
     "fromName": "shop-app-signup",
     "toName": "shop-app-main",
     "at": 1792297600000,
     "deliveredAt": 1792297600800,
     "readAt": 1792297601600,
     "state": "read",
     "text": "いま入力の検証を書いています。30 分ほどで出せます。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "session",
     "merged": false
    },
    {
     "id": "m-demo-0003-0000-4000-8000-000000000000",
     "msgId": "demo-0003-0000-4000-8000-000000000000",
     "convId": "t-70adb9b17963bc5a",
     "dir": "out",
     "fromName": "shop-app-signup",
     "toName": "shop-app-main",
     "at": 1792299280000,
     "deliveredAt": 1792299280800,
     "readAt": 1792299281600,
     "state": "read",
     "text": "会員登録の画面を仕上げました。確認してほしい点は次のとおりです。\n\n1. **メールアドレス**の入力欄は、確認用の欄と一致しないとき `送信` を押せないようにしました。\n2. パスワードは 8 文字以上、英字と数字を含むこと。弱いときは赤い文で理由を出します。\n3. 利用規約のリンクは別画面で開きます（戻ると入力は残ります）。\n\nテスト: `jsonui-test run tests/screens/signup` で 14 件すべて通りました。\niOS と Android のスクリーンショットは docs/screens/signup/ に置いてあります。\n<script>alert(1)</script> のような文字列も、そのまま文字として出ること（escape の見本）。\n残り: 住所の自動入力は次の列車で。",
     "cut": false,
     "summary": "会員登録の画面を仕上げた",
     "seen": "both",
     "via": "session",
     "merged": false
    },
    {
     "id": "m-demo-0004-0000-4000-8000-000000000000",
     "msgId": "demo-0004-0000-4000-8000-000000000000",
     "convId": "t-70adb9b17963bc5a",
     "dir": "in",
     "fromName": "shop-app-main",
     "toName": "shop-app-signup",
     "at": 1792299400000,
     "deliveredAt": 1792299400800,
     "readAt": null,
     "state": "delivered",
     "text": "ありがとう。住所の自動入力は次の列車で大丈夫です。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "session",
     "merged": false
    }
   ],
   "more": false
  },
  "a3 t-68f5487e3df0ef59": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "a3",
   "convId": "t-68f5487e3df0ef59",
   "items": [
    {
     "id": "u-toolu_demo_0005",
     "msgId": null,
     "convId": "t-68f5487e3df0ef59",
     "dir": "in",
     "fromName": "shop-app-main",
     "toName": "サブエージェント a3（jsonui-define）",
     "at": 1792298200000,
     "deliveredAt": 1792298200800,
     "readAt": 1792298201600,
     "state": "read",
     "text": "signup.spec.json の項目を 3 つ足して、検証を通してください。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "subagent",
     "merged": false
    },
    {
     "id": "u-toolu_demo_0006",
     "msgId": null,
     "convId": "t-68f5487e3df0ef59",
     "dir": "out",
     "fromName": "サブエージェント a3（jsonui-define）",
     "toName": "shop-app-main",
     "at": 1792298500000,
     "deliveredAt": 1792298500800,
     "readAt": 1792298501600,
     "state": "read",
     "text": "足しました。doc_validate_spec は緑です。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "parent",
     "merged": false
    }
   ],
   "more": false
  },
  "4f t-e7be89fd2788347b": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "4f",
   "convId": "t-e7be89fd2788347b",
   "items": [
    {
     "id": "m-demo-0008-0000-4000-8000-000000000000",
     "msgId": "demo-0008-0000-4000-8000-000000000000",
     "convId": "t-e7be89fd2788347b",
     "dir": "out",
     "fromName": "jsonui-agents-for-claude-4f-library-orchestrator-for-the-2.3.7-train",
     "toName": "shop-app-main",
     "at": 1792299520000,
     "deliveredAt": 1792299520800,
     "readAt": 1792299521600,
     "state": "read",
     "text": "2.3.7 の列車の範囲を決めました。トークの画面が入ります。",
     "cut": false,
     "summary": "2.3.7 の範囲",
     "seen": "both",
     "via": "session",
     "merged": false
    }
   ],
   "more": false
  },
  "d8 t-d74ea5e94db195e1": {
   "type": "talk.messages",
   "reqId": 0,
   "agentId": "d8",
   "convId": "t-d74ea5e94db195e1",
   "items": [
    {
     "id": "m-demo-0009-0000-4000-8000-000000000000",
     "msgId": "demo-0009-0000-4000-8000-000000000000",
     "convId": "t-d74ea5e94db195e1",
     "dir": "in",
     "fromName": "shop-app-main",
     "toName": "shop-app-payment",
     "at": 1792297000000,
     "deliveredAt": 1792297000800,
     "readAt": 1792297001600,
     "state": "read",
     "text": "決済の画面のテスト、止まっていますか？",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "session",
     "merged": false
    },
    {
     "id": "m-demo-0010-0000-4000-8000-000000000000",
     "msgId": "demo-0010-0000-4000-8000-000000000000",
     "convId": "t-d74ea5e94db195e1",
     "dir": "out",
     "fromName": "shop-app-payment",
     "toName": "shop-app-main",
     "at": 1792297120000,
     "deliveredAt": 1792297120800,
     "readAt": 1792297121600,
     "state": "read",
     "text": "シミュレーターを待っています。空いたら流します。",
     "cut": false,
     "summary": null,
     "seen": "both",
     "via": "session",
     "merged": false
    }
   ],
   "more": false
  }
 },
 "script": [
  {
   "t": 20,
   "frame": {
    "type": "talk.update",
    "agentId": "a0",
    "ops": [
     {
      "op": "message",
      "convId": "t-70adb9b17963bc5a",
      "message": {
       "id": "m-demo-0011-0000-4000-8000-000000000000",
       "msgId": "demo-0011-0000-4000-8000-000000000000",
       "convId": "t-70adb9b17963bc5a",
       "dir": "in",
       "fromName": "shop-app-signup",
       "toName": "shop-app-main",
       "at": 1792300020000,
       "deliveredAt": 1792300020700,
       "readAt": null,
       "state": "delivered",
       "text": "スクリーンショットを差し替えました。もう一度見てください。",
       "cut": false,
       "summary": "差し替え",
       "seen": "both",
       "via": "session",
       "merged": false
      }
     },
     {
      "op": "conv",
      "conv": {
       "id": "t-70adb9b17963bc5a",
       "owner": "a0",
       "peer": {
        "key": "b4",
        "agentId": "b4",
        "sessionId": "b47e0000-0000-4000-8000-0000000000b4",
        "name": "shop-app-signup",
        "kind": "session",
        "alive": true,
        "goneAt": null,
        "removeAt": null
       },
       "lastAt": 1792300020000,
       "preview": "スクリーンショットを差し替えました。もう一度見てください。",
       "lastDir": "in",
       "unread": 2,
       "count": 5
      }
     }
    ]
   }
  },
  {
   "t": 20,
   "frame": {
    "type": "talk.badges",
    "counts": {
     "a0": 3
    }
   }
  },
  {
   "t": 30,
   "frame": {
    "type": "talk.update",
    "agentId": "a0",
    "ops": [
     {
      "op": "message",
      "convId": "t-70adb9b17963bc5a",
      "message": {
       "id": "m-demo-0004-0000-4000-8000-000000000000",
       "msgId": "demo-0004-0000-4000-8000-000000000000",
       "convId": "t-70adb9b17963bc5a",
       "dir": "out",
       "fromName": "shop-app-main",
       "toName": "shop-app-signup",
       "at": 1792299400000,
       "deliveredAt": 1792299400800,
       "readAt": 1792300030000,
       "state": "read",
       "text": "ありがとう。住所の自動入力は次の列車で大丈夫です。",
       "cut": false,
       "summary": null,
       "seen": "both",
       "via": "session",
       "merged": false
      }
     }
    ]
   }
  },
  {
   "t": 45,
   "frame": {
    "type": "talk.update",
    "agentId": "a0",
    "ops": [
     {
      "op": "remove",
      "convId": "t-d74ea5e94db195e1",
      "reason": "peer-ended"
     }
    ]
   }
  }
 ]
};
