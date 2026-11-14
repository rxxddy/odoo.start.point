---
description: Promises, async/await, events, and manipulating the page.
---

# Async and the DOM

A browser runs your JavaScript on a single thread, and almost everything interesting (a server call, a timer, a click) happens later. Odoo's client is one long chain of "ask the server, wait, update the screen". This chapter covers the event loop, promises, `async`/`await`, error handling for concurrent work, and the DOM: selecting elements, handling events, and changing the page safely. The last section maps these onto OWL, which does most DOM work for you, so you know what it saves you from and when you still need the raw API.

The Node-runnable snippets were executed with Node.js 20+ as `.mjs` files. DOM snippets run in a browser console or in a page; they are marked.

## The event loop

JavaScript has one call stack. A long synchronous loop blocks everything, including rendering and clicks. Asynchronous operations hand work to the environment (timers, network, file system) and register a callback; when the stack is empty, the event loop picks the next callback from a queue.

There are two queues you need to distinguish:

- **Macrotasks**: timers (`setTimeout`, `setInterval`), I/O callbacks, user events.
- **Microtasks**: promise callbacks (`then`, `await` continuations) and `queueMicrotask`. All pending microtasks run before the next macrotask, and before the browser renders.

```js
console.log("1 sync");
setTimeout(() => console.log("5 timeout"), 0);
Promise.resolve().then(() => console.log("3 microtask"));
queueMicrotask(() => console.log("4 microtask 2"));
(async () => {
  console.log("2 async start (runs synchronously until the first await)");
  await null;
  console.log("4b after await (a microtask)");
})();
console.log("2b sync end");
```

Output order: `1 sync`, `2 async start...`, `2b sync end`, `3 microtask`, `4 microtask 2`, `4b after await`, `5 timeout`. Even with a delay of 0 the timeout runs last, because the synchronous code and the whole microtask queue go first.

Two things follow. An `async` function runs synchronously until its first `await`. And a microtask loop that keeps scheduling microtasks starves rendering, so a `while` with `await` on an already-resolved promise can freeze the page.

## Callbacks, and why promises replaced them

The old style passes a function to be called when the work is done:

```js
setTimeout(() => console.log("later"), 100);
```

Nesting a few of these produces a pyramid where each level handles its own errors. A promise is an object that represents a value that will exist later, and it can be passed around, combined, and awaited.

A promise has three states: pending, fulfilled (with a value), rejected (with a reason). It settles once and never changes.

```js
const sleep = (ms, value, fail = false) =>
  new Promise((resolve, reject) =>
    setTimeout(() => (fail ? reject(new Error(value)) : resolve(value)), ms)
  );

sleep(10, "a")
  .then((v) => v + "b")          // returns a value: next then gets it
  .then((v) => sleep(10, v + "c"))   // returns a promise: next then waits for it
  .then(console.log)             // abc
  .catch((e) => console.log("failed", e.message))
  .finally(() => console.log("always"));
```

A `.then` returns a new promise. Whatever the callback returns (or throws) settles that new promise. A `.catch` at the end catches a rejection from any step before it.

## async/await

`async`/`await` is promise syntax that reads like synchronous code.

```js
async function loanReport() {
  const a = await sleep(10, "A");
  const b = await sleep(10, "B");
  return a + b;                 // an async function always returns a promise
}
loanReport().then(console.log);  // AB
```

- `async function f()` returns a promise. `return x` resolves it with `x`; a `throw` rejects it.
- `await p` pauses the function until `p` settles, then gives the fulfilled value or throws the rejection reason. It does not block the thread; other code runs meanwhile.
- `await` is allowed only inside an `async` function or at the top level of an ES module.
- Arrow functions and methods can be async: `const f = async () => {}`, `async refresh() {}`.

### Errors

Use `try`/`catch`/`finally`:

```js
async function safe() {
  try {
    await sleep(5, "server said no", true);
  } catch (err) {
    console.log("caught:", err.message);
    return "fallback";
  } finally {
    console.log("cleanup");        // always runs: reset a loading flag here
  }
}
safe().then(console.log);
```

The `finally` block is the right place to reset a "loading" state, so a failed request does not leave a spinner on forever.

The main hazard is forgetting `await` or forgetting to handle a rejection. A promise whose rejection nobody handles ends as an "unhandled rejection": the browser logs it, and Node (15 and later) terminates the process. In a UI the failure is silent: the button just does nothing.

```js
async function save() { throw new Error("nope"); }
save();                 // missing await and catch: unhandled rejection
await save();           // propagates to the caller, which must handle it
```

Odoo's RPC layer turns server errors into rejections with an error object, and the web client shows a dialog for uncaught ones. In a component method, catch only what you can act on and let the rest propagate to that global handler.

### Sequential versus parallel

Awaiting in sequence adds the durations. Starting the work first and awaiting together overlaps it.

```js
console.time("seq");
await sleep(50, "a");
await sleep(50, "b");
console.timeEnd("seq");   // about 100 ms

console.time("par");
const results = await Promise.all([sleep(50, "a"), sleep(50, "b")]);
console.timeEnd("par");   // about 50 ms
console.log(results);     // [ 'a', 'b' ]
```

The combinators:

| Function | Resolves when | Rejects when |
|----------|---------------|--------------|
| `Promise.all([...])` | all fulfil, with an array of values in input order | the first one rejects |
| `Promise.allSettled([...])` | all settle, with `{status, value\|reason}` objects | never |
| `Promise.race([...])` | the first settles (fulfil or reject) | first to settle rejects |
| `Promise.any([...])` | the first fulfils | all reject (`AggregateError`) |

```js
console.log(await Promise.allSettled([sleep(5, "ok"), sleep(5, "bad", true)]));
// [ { status: 'fulfilled', value: 'ok' }, { status: 'rejected', reason: Error: bad ... } ]
try {
  await Promise.all([sleep(5, "ok"), sleep(5, "bad", true)]);
} catch (e) { console.log("caught", e.message); }     // caught bad
console.log(await Promise.race([sleep(30, "slow"), sleep(5, "fast")]));   // fast
```

Use `all` when every result is required, `allSettled` when partial failure is acceptable (for example, loading optional side panels). Note that `Promise.all` does not cancel the others when one rejects; they keep running.

A trap with loops: `array.forEach(async (x) => { await work(x); })` does not wait for anything, because `forEach` ignores the returned promises. Use `for...of` with `await` for sequential work, or `await Promise.all(array.map(async (x) => work(x)))` for parallel.

```js
for (const book of books) {
  await returnBook(book);              // one at a time, in order
}
await Promise.all(books.map(returnBook));   // all at once; mind server load
```

For many items, concurrent calls to one server hit database limits and Odoo's worker limits; batch in the ORM call instead of sending hundreds of requests.

### Timers, debounce, and cancellation

```js
const id = setTimeout(fn, 300);  clearTimeout(id);
const tick = setInterval(fn, 1000);  clearInterval(tick);
```

Debounce delays a call until input has settled. It is the standard fix for "search on every keystroke":

```js
function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
const search = debounce((q) => console.log("search for", q), 20);
search("d"); search("du"); search("dun");   // prints once: search for dun
```

To abandon a request, use an `AbortController`. `fetch` accepts its `signal`:

```js
const controller = new AbortController();
const promise = fetch("/library/api/books", { signal: controller.signal });
controller.abort();                // promise rejects with an AbortError
promise.catch((e) => console.log(e.name));   // AbortError
```

Components that start requests should cancel or ignore results when they are destroyed, so a late response does not update a component that no longer exists.

## Talking to a server

`fetch` returns a promise of a `Response`. A response is available when the headers arrive; reading the body is another promise. `fetch` rejects only on network failure; an HTTP 404 or 500 is a successful fetch with `response.ok === false`.

```js
async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} for ${url}`);
  }
  return response.json();
}

const created = await getJson("/library/api/books", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ title: "Dune" }),
});
```

The HTTP chapter covers methods, headers, and JSON-RPC in detail. In Odoo's web client you rarely use `fetch` directly for model data. The framework gives you the ORM service for CRUD and an `rpc` helper for custom routes, both returning promises:

```js
// in an OWL component, fragment
setup() {
  this.orm = useService("orm");
}
async loadBooks() {
  const books = await this.orm.searchRead(
    "library.book", [["year", "<", 2000]], ["name", "year"], { limit: 20 }
  );
  this.state.books = books;
}
```

`searchRead(model, domain, fields, kwargs)` is part of the ORM service in the versions covered by this book.

{% hint style="info" %}
Versions: how you call a custom route differs by release. In Odoo 16 the `rpc` service is obtained with `useService("rpc")`; from 17 there is also a standalone `rpc` function you can import from the `web` module's network folder. Verify the exact import path in your version's source before copying.
{% endhint %}

Plain `fetch` is appropriate for non-JSON endpoints (file downloads, static assets) and for code outside the web client, such as a standalone portal script. Remember that Odoo controllers of `type="http"` that accept POST need a CSRF token; `type="json"` routes use the JSON-RPC envelope described in the next chapter.

## The DOM

The DOM is the browser's in-memory tree of the page. JavaScript reads and changes it; the browser re-renders. `document` is the root and every element is an object.

### Selecting

```js
// browser
const title = document.querySelector("h1");                  // first match or null
const rows = document.querySelectorAll("table.items tr");     // NodeList (static)
const byId = document.getElementById("total");
const inCard = card.querySelector(".price");                  // scoped to an element
const row = event.target.closest("tr");                       // nearest ancestor match
Array.from(rows).map((r) => r.dataset.id);                    // NodeList to array
```

`querySelector` returns `null` if nothing matches, so `document.querySelector(".x").textContent` throws when `.x` is absent. Guard with `?.`.

### Reading and changing

```js
// browser
el.textContent = "Dune";                    // text; safe, no HTML parsing
el.innerHTML = "<b>Dune</b>";               // parses HTML; dangerous with untrusted text
el.classList.add("text-muted");
el.classList.toggle("d-none", isHidden);
el.setAttribute("href", "/my/loans/1");
el.dataset.bookId = "7";                    // writes data-book-id="7"
el.style.display = "none";
const input = document.querySelector("input[name=q]");
console.log(input.value);                   // current value, a string
```

Creating and inserting:

```js
// browser
const li = document.createElement("li");
li.textContent = "Emma";
list.append(li);                  // end of list
list.prepend(li.cloneNode(true)); // start
list.insertAdjacentHTML("beforeend", "<li>Static markup you wrote</li>");
li.remove();
```

#### innerHTML and cross-site scripting

If any part of an `innerHTML` string comes from a user (a book title, a partner name, a note), an attacker can put `<img src=x onerror=...>` there and run script in the viewer's session, including an administrator's. Use `textContent` for text. When you must insert markup, build elements with `createElement`, or sanitise through the framework's `Markup` mechanism. In OWL and QWeb, `t-out` escapes by default, and only values marked as markup are inserted raw; fields of type `Html` are the sanctioned source of markup.

### Events

```js
// browser
const button = document.querySelector("button.save");
button.addEventListener("click", (event) => {
  event.preventDefault();       // stop default (link navigation, form submit)
  console.log("clicked", event.target);
});
```

An event travels in three phases: capture (window down to the target), target, and bubble (target back up to window). Most handlers run in the bubble phase. `event.stopPropagation()` stops it from travelling further, and should be rare, because it breaks other code listening higher up (including Odoo's own global handlers).

Because events bubble, one listener on a container can serve many children. This is **event delegation**, and it is the right tool for lists that change:

```js
// browser
document.querySelector("table.loans").addEventListener("click", (event) => {
  const btn = event.target.closest("button[data-action='return']");
  if (!btn) return;
  const loanId = Number(btn.closest("tr").dataset.id);
  console.log("return loan", loanId);
});
```

Remove listeners you add to long-lived objects (`window`, `document`) when the owner goes away, or they leak and fire on stale state:

```js
// browser
function onResize() { /* ... */ }
window.addEventListener("resize", onResize);
// later
window.removeEventListener("resize", onResize);
```

The listener passed to `removeEventListener` must be the same function reference. An inline arrow cannot be removed, so keep it in a variable. `AbortController` gives a tidy alternative: pass `{ signal }` when adding, and `controller.abort()` removes all of them.

Common events: `click`, `input` (every change to a field value), `change` (on commit), `submit`, `keydown`, `focus`/`blur`, `DOMContentLoaded`, `scroll`, `resize`. `input` fires per keystroke, so combine with debounce for server calls.

### Observers

For things that happen later without an event, observers watch the DOM:

```js
// browser
const mo = new MutationObserver((records) => console.log(records.length, "changes"));
mo.observe(container, { childList: true, subtree: true });
// mo.disconnect() when done

const io = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) console.log("visible", e.target);
});
io.observe(document.querySelector(".card"));
```

`MutationObserver` reports DOM changes; `IntersectionObserver` reports visibility (lazy loading, infinite scroll). Both batch and run as microtasks, so they do not fire inside your synchronous code.

### Layout reads and writes

Reading `offsetHeight` or `getBoundingClientRect()` forces the browser to compute layout. Alternating reads and writes in a loop makes this happen repeatedly ("layout thrashing"). Read everything, then write everything.

### Waiting for the page

A script in a page head runs before the body exists. Either place the script at the end, use `defer`, or listen for readiness:

```js
// browser
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
```

In Odoo you do not write this; the framework mounts components when the page is ready and calls your hooks at the right time.

## OWL does the DOM for you

In an OWL component the DOM is a function of state. You change state; the framework patches the DOM. Compare a hand-written counter with the component form:

```js
// browser, manual DOM
let count = 0;
const label = document.querySelector("#count");
document.querySelector("#plus").addEventListener("click", () => {
  count++;
  label.textContent = String(count);
});
```

```xml
<!-- OWL template (fragment) -->
<t t-name="library.Counter">
    <button class="btn btn-primary" t-on-click="increment">
        Count: <t t-out="state.count"/>
    </button>
</t>
```

```js
// OWL component (fragment)
import { Component, useState } from "@odoo/owl";
export class Counter extends Component {
  static template = "library.Counter";
  setup() { this.state = useState({ count: 0 }); }
  increment() { this.state.count++; }
}
```

What you stop doing: selecting elements, creating nodes, keeping the DOM in sync, removing listeners (`t-on-*` handlers are managed with the component's life). What you still need:

- `useRef("name")` with `t-ref="name"` to get an element when you need a native API (focus, measuring, a third-party widget).
- Lifecycle hooks for effects that touch the outside world: `onMounted(() => ...)` after the first render, `onWillUnmount(() => ...)` to remove what you added, `onWillStart(async () => ...)` to load data before the first render, `onWillUpdateProps` when inputs change.
- `useEffect`-style hooks (available in the web library) to run code when specific dependencies change.

```js
// fragment
setup() {
  this.inputRef = useRef("search");
  onMounted(() => this.inputRef.el.focus());
  onWillStart(async () => {
    this.books = await this.orm.searchRead("library.book", [], ["name"]);
  });
}
```

`onWillStart` accepts an async callback and the component does not render until it settles, which is how you load initial data. Setting `this.state.x` in `onMounted` triggers a second render, which is fine for data that arrives later but flickers for data you could have loaded in `onWillStart`.

Rule: if you find yourself calling `document.querySelector` inside an OWL component, stop and check whether a `t-ref`, a `t-on-*`, or state can do it.

## Pitfalls

- **Forgotten `await`.** `const books = this.orm.searchRead(...)` gives a promise, and `books.length` is `undefined`. Linters with a "floating promise" rule catch it.
- **`forEach(async ...)`.** Does not wait. Use `for...of` or `Promise.all(map(...))`.
- **Sequential awaits that should be parallel**, and the opposite: parallel requests that must be ordered (a write followed by a read of the same record).
- **Treating `fetch` as failing on 4xx/5xx.** It does not. Check `response.ok`.
- **Swallowed errors.** `catch (e) {}` hides bugs. Catch to recover or to add context, then rethrow if you cannot recover.
- **State after unmount.** A response arriving after the component is destroyed writes into dead state. Cancel with `AbortController` or check a flag.
- **`innerHTML` with user data.** Cross-site scripting. Use `textContent` or escaped templates.
- **`querySelector` returning `null`.** Elements may not exist yet or at all.
- **Listeners that are never removed**, especially on `window` and `document`, and listeners registered inside a component method that runs on every render.
- **`stopPropagation` as a fix.** It hides the event from code that depended on it. Prefer checking `event.target`.
- **Blocking the thread.** A big synchronous loop over thousands of records freezes the page. Process on the server, or chunk the work with `await` between chunks.
- **Updating state in a loop and expecting an immediate DOM change.** Rendering is batched; DOM reflects state after the next render, not on the next line.

## Try it

**1. Order of output.** Predict the output order, then run it.

```js
setTimeout(() => console.log("A"), 0);
Promise.resolve().then(() => console.log("B"));
(async () => { console.log("C"); await 1; console.log("D"); })();
console.log("E");
```

<details>
<summary>Solution</summary>

`C`, `E`, `B`, `D`, `A`. `C` runs synchronously inside the async function until `await`; `E` follows. Then the microtask queue drains in registration order: the `then` callback (`B`), then the continuation after `await` (`D`). The timeout, a macrotask, goes last.
</details>

**2. Parallel loading.** You have `loadBooks()`, `loadMembers()`, and `loadSettings()`, all returning promises; settings are optional. Write one async function that loads all three in parallel and returns `{ books, members, settings }`, with `settings` as `null` when it fails.

<details>
<summary>Solution</summary>

```js
async function loadAll() {
  const [books, members, settings] = await Promise.all([
    loadBooks(),
    loadMembers(),
    loadSettings().catch(() => null),
  ]);
  return { books, members, settings };
}
```

The `.catch` on the optional request converts its rejection to `null` so `Promise.all` does not fail; a failure of books or members still rejects the whole call.
</details>

**3. Fix the loop.** This function returns before the books are returned. Fix it in two ways.

```js
async function returnAll(books) {
  books.forEach(async (b) => { await returnBook(b); });
}
```

<details>
<summary>Solution</summary>

Sequential:

```js
async function returnAll(books) {
  for (const b of books) await returnBook(b);
}
```

Parallel:

```js
async function returnAll(books) {
  await Promise.all(books.map((b) => returnBook(b)));
}
```

`forEach` ignores the promises its callback returns, so the outer function finishes immediately.
</details>

**4. Delegation.** A table of loans gets rows added dynamically. Write one listener so that clicking any `button.renew` inside a row calls `renew(id)`, where `id` is the row's `data-id`.

<details>
<summary>Solution</summary>

```js
// browser
document.querySelector("table.loans").addEventListener("click", (event) => {
  const button = event.target.closest("button.renew");
  if (!button) return;
  renew(Number(button.closest("tr").dataset.id));
});
```

The listener lives on the table, which exists once, so rows added later work without new listeners. `closest` handles clicks on elements inside the button, such as an icon.
</details>

**5. Debounced search with cancellation.** Write `makeSearcher(url)` returning a function `search(q)` that waits 200 ms after the last call, aborts any request still in flight, and returns nothing. Sketch it with `fetch` and `AbortController`.

<details>
<summary>Solution</summary>

```js
function makeSearcher(url, onResult) {
  let timer, controller;
  return (q) => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const res = await fetch(`${url}?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        if (res.ok) onResult(await res.json());
      } catch (err) {
        if (err.name !== "AbortError") throw err;
      }
    }, 200);
  };
}
```

`encodeURIComponent` protects the query string from characters such as `&` and spaces. Aborted requests reject with `AbortError`, which is expected and ignored; other errors propagate.
</details>
