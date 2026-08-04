/**
 * LINEの「投稿する」ボタンを受け取って GitHub Actions を起動する中継役。
 *
 * なぜこれが要るか：
 *   GitHub Actions は「決まった時刻に動く」ことはできるが、
 *   LINEからのボタン押下（Webhook）を受け取ることができない。
 *   受け口が必要で、Apps Script は無料で24時間動く受け口になる。
 *
 * 設置手順は README.md の「4. LINE承認ボタンの受け口」を参照。
 *
 * スクリプトプロパティ（プロジェクトの設定 → スクリプト プロパティ）に
 * 次の4つを入れること。コードには直接書かない。
 *   LINE_CHANNEL_ACCESS_TOKEN … LINE Developers のチャネルアクセストークン
 *   GH_PAT                    … GitHub の Personal Access Token (repo権限)
 *   GH_REPO                   … 例 chikatabi/chikatabi-ig-bot
 *   ALLOWED_USER_ID           … CHIKA自身のLINEユーザーID（他人が押せないように）
 */

function prop(name) {
  return PropertiesService.getScriptProperties().getProperty(name);
}

function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    (body.events || []).forEach(handleEvent);
  } catch (err) {
    console.error(err);
  }
  // LINEには常に200を返す（エラーを返すと再送が続くため）
  return ContentService.createTextOutput(JSON.stringify({ ok: true }))
    .setMimeType(ContentService.MimeType.JSON);
}

function handleEvent(ev) {
  if (ev.type !== 'postback') return;

  // 本人以外のボタン押下は無視する。これが無いと、
  // この公式アカウントを友だち追加した誰でも投稿できてしまう。
  var allowed = prop('ALLOWED_USER_ID');
  if (allowed && ev.source && ev.source.userId !== allowed) {
    reply(ev.replyToken, '権限がありません。');
    return;
  }

  var params = parseQuery(ev.postback.data);   // act, date, i
  if (params.act === 'reject') {
    reply(ev.replyToken, '見送りました。投稿しません。');
    return;
  }
  if (params.act !== 'approve') return;

  var res = dispatchGitHub(params.date, params.i);
  if (res.getResponseCode() === 204) {
    reply(ev.replyToken, '承認しました。投稿処理を開始します（完了したらお知らせします）。');
  } else {
    reply(ev.replyToken, '起動に失敗しました：' + res.getResponseCode() + ' ' + res.getContentText());
  }
}

/** "act=approve&date=2026-08-05&i=0" → {act:..., date:..., i:...} */
function parseQuery(data) {
  var out = {};
  (data || '').split('&').forEach(function (pair) {
    var kv = pair.split('=');
    if (kv.length === 2) out[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1]);
  });
  return out;
}

/** GitHub の repository_dispatch を叩いて publish.yml を起動する */
function dispatchGitHub(date, index) {
  return UrlFetchApp.fetch(
    'https://api.github.com/repos/' + prop('GH_REPO') + '/dispatches',
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + prop('GH_PAT'),
        Accept: 'application/vnd.github+json'
      },
      payload: JSON.stringify({
        event_type: 'ig-publish',
        client_payload: { date: date, index: index }
      }),
      muteHttpExceptions: true
    }
  );
}

function reply(replyToken, text) {
  UrlFetchApp.fetch('https://api.line.me/v2/bot/message/reply', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + prop('LINE_CHANNEL_ACCESS_TOKEN') },
    payload: JSON.stringify({
      replyToken: replyToken,
      messages: [{ type: 'text', text: text }]
    }),
    muteHttpExceptions: true
  });
}

/**
 * 自分のLINEユーザーIDを調べるための一時的な関数。
 * この関数を残したまま何かメッセージを送ると、実行ログにIDが出る。
 * ALLOWED_USER_ID / LINE_TO_USER_ID に設定したら、この関数は消してよい。
 */
function whoAmI(ev) {
  console.log('userId = ' + (ev && ev.source && ev.source.userId));
}
