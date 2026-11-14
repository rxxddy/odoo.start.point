---
description: "Modern JavaScript: variables, functions, modules, classes."
---

# JavaScript fundamentals

Odoo's web client, website, and portal are written in modern JavaScript: ES modules, classes, arrow functions, destructuring, and (from version 16 on) the OWL component framework. A Python developer can read most of it after a day and still be bitten for weeks by `this`, by `==`, and by `await` forgotten in the wrong place. This chapter teaches the language as it is used in current Odoo code, and ends by showing what an OWL component looks like so the next parts of the book read naturally.

Every runnable snippet was executed with Node.js (version 20 or later). Save a snippet as `demo.mjs` and run `node demo.mjs`; the `.mjs` extension makes Node treat the file as an ES module, which is the same module system Odoo uses. Browser-only examples are marked.

## Values, variables, and types

Declare with `const` by default and `let` when you reassign. Do not use `var`.

```js
const name = "Dune";      // cannot be rebound
let copies = 3;           // can be rebound
copies += 1;
// name = "Emma";         // TypeError: Assignment to constant variable
```

`const` stops rebinding, not mutation: a `const` array can still be pushed to.

Primitive types: `string`, `number` (one type for integers and floats, a 64-bit float), `bigint`, `boolean`, `undefined`, `null`, `symbol`. Everything else is an object: plain objects, arrays, functions, dates, maps, sets.

```js
console.log(typeof "x", typeof 1, typeof true, typeof undefined);   // string number boolean undefined
console.log(typeof null, typeof [], typeof {}, typeof (() => 1));   // object object object function
console.log(Array.isArray([]));                                      // true
console.log(0.1 + 0.2);                                              // 0.30000000000000004
```

Two consequences. `typeof null` is `"object"`, a historical accident, so test for null explicitly. And all numbers are floats, so money must be handled in integer cents or by the server, never accumulated as JavaScript floats. Odoo monetary values arrive as numbers already rounded by the server; display them with the framework's formatting helpers instead of `toFixed` where available.

`undefined` means "no value was provided" (a missing property, an uninitialised variable, a function without `return`). `null` means "deliberately empty". Python's `None` maps to JSON `null`.

### Equality and truthiness

Use `===` and `!==`. The loose `==` converts types and produces results nobody remembers:

```js
console.log(0 == "", "1" == 1, null == undefined, [] == false);  // true true true true
console.log(0 === "", "1" === 1, null === undefined);            // false false false
console.log(NaN === NaN, Object.is(NaN, NaN));                   // false true
```

Falsy values are `false`, `0`, `-0`, `""`, `null`, `undefined`, `NaN`, `0n`. Everything else is truthy, including `[]`, `{}`, and `"0"`. This differs from Python, where an empty list is falsy:

```js
if ([]) console.log("empty array is truthy");
if (!Array.isArray(list) || list.length === 0) { /* check emptiness explicitly */ }
```

Two operators to know:

```js
console.log(0 || "default");      // "default"  (|| replaces any falsy value)
console.log(0 ?? "default");      // 0          (?? replaces only null and undefined)
const user = { profile: null };
console.log(user.profile?.name);  // undefined  (optional chaining, no TypeError)
console.log(user.profile?.name ?? "anonymous");  // anonymous
let cache;
cache ??= new Map();              // assign only if null or undefined
```

Use `??` when `0` or `""` are legitimate values. `?.` also works on calls (`obj.method?.()`) and indexes (`list?.[0]`).

### Strings

Template literals use backticks, support embedded expressions and multiple lines:

```js
const book = { title: "Dune", year: 1965 };
const line = `${book.title} (${book.year ?? "n/a"})`;
console.log(line.toUpperCase(), line.length, line.includes("Dune"));
console.log("a-b-c".split("-"), "a-b-c".replaceAll("-", "+"), "7".padStart(3, "0"));
```

Strings are immutable and compared by value. In Odoo the translation helper `_t("text")` marks a string for translation. It needs a literal string, not a template literal with embedded expressions, because the extractor reads the source text. The details sit in the frontend part.

## Functions

Three forms, all common:

```js
function add(a, b) { return a + b; }            // declaration, hoisted
const mul = function (a, b) { return a * b; };  // expression
const sub = (a, b) => a - b;                    // arrow function
```

Arrow functions with a single expression return it implicitly; with a block they need `return`. Returning an object literal from an arrow needs parentheses: `() => ({ a: 1 })`.

Parameters can have defaults and a rest parameter collects the remainder:

```js
function loan(book, { days = 14, renew = false } = {}, ...notes) {
  return { book, days, renew, notes };
}
console.log(loan("Dune"));
console.log(loan("Dune", { days: 7 }, "late fee", "call member"));
```

Passing an options object, with destructuring in the parameter list, is the idiom for any function with more than two or three parameters. Odoo code does it everywhere.

Functions are values. You pass them, return them, and store them in objects:

```js
const apply = (fn, x) => fn(x);
console.log(apply((n) => n * 2, 21));  // 42
```

### Scope and closures

`let` and `const` are block scoped; `var` is function scoped and hoisted, which creates a classic bug:

```js
const withVar = [];
for (var i = 0; i < 3; i++) withVar.push(() => i);
console.log(withVar.map((f) => f()));   // [ 3, 3, 3 ]   one shared i

const withLet = [];
for (let j = 0; j < 3; j++) withLet.push(() => j);
console.log(withLet.map((f) => f()));   // [ 0, 1, 2 ]   a fresh j per iteration
```

A closure is a function that remembers the variables of the scope where it was created, even after that scope has finished:

```js
function makeCounter() {
  let n = 0;
  return {
    inc: () => ++n,
    get value() { return n; },
  };
}
const c = makeCounter();
c.inc(); c.inc();
console.log(c.value);   // 2
```

`n` is private: only the two functions can reach it. Closures are the reason event handlers can use variables from the function that registered them, and the reason a stale variable in a handler is a common bug: the closure captures the variable, and in frameworks that re-run code per render, you can capture an old value.

A useful closure pattern is memoising:

```js
function once(fn) {
  let done = false, result;
  return (...args) => (done ? result : ((done = true), (result = fn(...args))));
}
const init = once((x) => x * 2);
console.log(init(2), init(5));   // 4 4
```

## `this`

`this` is the object a function is called on, decided at call time, not at definition time. This is the largest difference from Python's `self`, which is an explicit parameter.

```js
const obj = {
  name: "a",
  hello() { return this?.name; },
};
console.log(obj.hello());      // "a"   called as a method: this is obj
const detached = obj.hello;
console.log(detached());       // undefined   no object: this is undefined (module code is strict)
```

Rules, in order:

1. `new F()`: `this` is the new object.
2. `obj.method()`: `this` is `obj`.
3. A plain call `fn()`: `this` is `undefined` in modules and strict mode (in sloppy scripts it was the global object).
4. `fn.call(x, ...)`, `fn.apply(x, [...])`, `fn.bind(x)`: `this` is `x`.
5. **Arrow functions have no `this` of their own.** They use the `this` of the enclosing code, fixed at definition.

Rule 5 is why arrows fit callbacks inside methods:

```js
class Timer {
  seconds = 0;
  start() {
    const id = setInterval(() => {
      this.seconds++;          // arrow: this is the Timer instance
      if (this.seconds === 3) { clearInterval(id); console.log("done", this.seconds); }
    }, 10);
  }
}
new Timer().start();
```

With `function () { this.seconds++ }` the `this` would be wrong. The failure mode for the reverse, passing a method as a callback, is just as common:

```js
class Counter {
  count = 0;
  inc = () => { this.count++; };   // class field holding an arrow: bound once per instance
  dec() { this.count--; }          // normal method: depends on the caller
}
const k = new Counter();
const { inc, dec } = k;
inc();
console.log(k.count);              // 1  works
try { dec(); } catch (e) { console.log(e.constructor.name); }   // TypeError: this is undefined
```

In OWL components, handlers referenced from templates (`t-on-click="onClick"`) are bound to the component for you, so you can write ordinary methods. Handlers you register yourself on a DOM node or a timer in `setup` should be arrows or explicitly bound.

## Objects

```js
const book = { title: "Dune", year: 1965, tags: ["sf"] };
book.author = "Herbert";          // add
delete book.year;                 // remove
console.log("title" in book, Object.keys(book), Object.values(book));
console.log(Object.entries(book).map(([k, v]) => `${k}=${v}`).join("&"));
console.log(Object.fromEntries([["a", 1], ["b", 2]]));   // { a: 1, b: 2 }
```

Shorthand and computed keys:

```js
const title = "Dune", field = "year";
const rec = { title, [field]: 1965, describe() { return `${this.title}`; } };
```

Objects are references: assigning copies the reference, not the content.

```js
const a = { n: 1, inner: { x: 1 } };
const b = a;                  // same object
const shallow = { ...a };     // new top level, shared inner
const deep = structuredClone(a);   // full copy (no functions)
shallow.inner.x = 9;
console.log(a.inner.x);       // 9: shallow copy shares the nested object
console.log(deep.inner.x);    // 1
```

`JSON.parse(JSON.stringify(x))` is the older deep copy trick; it loses `undefined`, functions, and turns dates into strings. Prefer `structuredClone`.

The `Map` and `Set` types are better than plain objects for dynamic keys and uniqueness:

```js
const m = new Map([["a", 1]]);
m.set("b", 2);
console.log([...m], m.size, m.get("a"), m.has("z"));
console.log([...new Set([1, 1, 2, 3, 3])]);   // [ 1, 2, 3 ]
```

## Arrays

The array methods replace most loops. They return new arrays and do not mutate unless stated.

```js
const loans = [
  { member: "Ann", book: "Dune", days: 3 },
  { member: "Bob", book: "Emma", days: 10 },
  { member: "Ann", book: "Ulysses", days: 7 },
];

loans.filter((l) => l.days > 5).map((l) => l.book);      // [ 'Emma', 'Ulysses' ]
loans.find((l) => l.member === "Bob");                    // first match or undefined
loans.some((l) => l.days > 9);                            // true
loans.every((l) => l.days > 0);                           // true
loans.map((l) => l.days).reduce((sum, d) => sum + d, 0);  // 20
loans.at(-1).book;                                        // 'Ulysses'
loans.flatMap((l) => [l.member, l.book]);                 // flattened one level
```

Grouping with `reduce`, the long-standing form, and totals per key:

```js
const totals = loans.reduce(
  (acc, { member, days }) => ({ ...acc, [member]: (acc[member] ?? 0) + days }),
  {}
);
console.log(totals);   // { Ann: 10, Bob: 10 }
```

Newer runtimes also have `Object.groupBy(loans, (l) => l.member)`. It is not available in the oldest browsers, so check the browsers you support before using it in a module that ships to users.

Mutating methods: `push`, `pop`, `shift`, `unshift`, `splice`, `sort`, `reverse`. `sort` sorts as strings by default:

```js
console.log([10, 9, 1].sort());                 // [ 1, 10, 9 ]
console.log([10, 9, 1].sort((a, b) => a - b));  // [ 1, 9, 10 ]
```

Another classic trap:

```js
console.log(["1", "2", "3"].map(parseInt));     // [ 1, NaN, NaN ]  map passes (value, index)
console.log(["1", "2", "3"].map(Number));       // [ 1, 2, 3 ]
```

Iterate with `for...of` (values) or `Object.entries` for pairs. Avoid `for...in` over arrays: it yields keys and inherited properties.

```js
for (const [i, loan] of loans.entries()) console.log(i, loan.book);
```

There is no negative indexing with brackets; `arr[-1]` is `undefined`. Use `.at(-1)`.

## Destructuring, spread, and rest

Destructuring unpacks arrays and objects into variables:

```js
const [first, , third = "none", ...others] = ["a", "b", undefined, "d", "e"];
console.log(first, third, others);   // a none [ 'd', 'e' ]

const { title, author: writer = "?", meta: { pages } = { pages: 0 } } =
  { title: "Dune" };
console.log(title, writer, pages);   // Dune ? 0
```

Spread expands an iterable or object into another one:

```js
const a = [1, 2], b = [...a, 3];                  // [1, 2, 3]
const defaults = { days: 14, renew: false };
const options = { ...defaults, days: 7 };         // later keys win
const { id, ...rest } = { id: 1, x: 2, y: 3 };    // rest = { x: 2, y: 3 }
```

The pattern `{ ...state, field: newValue }` produces a changed copy without mutating the original. It is how you update objects in code that must not mutate (for example, a value passed in as props).

Swap two variables: `[x, y] = [y, x]`.

## Control flow in brief

```js
if (a) { } else if (b) { } else { }
switch (state) { case "draft": /* ... */ break; default: break; }
for (let i = 0; i < n; i++) { }
for (const x of iterable) { }
while (cond) { }
try { risky(); } catch (err) { handle(err); } finally { cleanup(); }
```

Ternary: `cond ? a : b`. Short-circuit: `ready && start()`. Labels exist for breaking out of nested loops (`outer: for (...) { ... continue outer; }`), rarely needed.

Errors are objects: `throw new Error("message")`. Throwing strings loses the stack trace.

```js
try {
  JSON.parse("{bad json}");
} catch (err) {
  console.log(err.name, err.message);   // SyntaxError ...
}
```

## Classes

```js
class Book {
  static count = 0;     // class-level
  #id;                  // private field
  constructor(title, { author = "?", year } = {}) {
    this.title = title;
    this.author = author;
    this.year = year;
    this.#id = ++Book.count;
  }
  get label() { return `${this.title} (${this.year ?? "n/a"})`; }
  get id() { return this.#id; }
  toString() { return this.label; }
  static fromObject(o) { return new Book(o.title, o); }
}

class Ebook extends Book {
  constructor(title, opts) {
    super(title, opts);                 // must be called before using this
    this.format = opts?.format ?? "epub";
  }
  get label() { return `${super.label} [${this.format}]`; }
}

const e = new Ebook("Dune", { year: 1965 });
console.log(e.label, e.id, String(e));        // Dune (1965) [epub] 1 Dune (1965) [epub]
console.log(e instanceof Book, Object.getPrototypeOf(Ebook) === Book);
```

Compared to Python classes: the constructor is `constructor`, `super(...)` must run before `this` is used in a subclass, methods are defined without `self`, `static` members belong to the class, getters are declared with `get`, and `#name` fields are truly private. Class fields (`count = 0;`) are initialised per instance before the constructor body.

Underneath, classes are syntax over prototypes: methods live on `Class.prototype`, and an instance finds a missing property by walking the prototype chain. You can ignore this until you read framework code that patches a method; the `patch` helper in Odoo's frontend replaces methods on a class prototype and calls the original through `super`.

Mixed-in behaviour via functions that return classes is also used in framework code, but you will write plain subclasses 95% of the time. Composition (holding a helper object) is usually simpler than deep inheritance.

## Modules

A module is a file. `export` names what is public; `import` brings names in.

```js
// math.mjs
export const TAX = 0.2;
export function net(gross) { return gross / (1 + TAX); }
export default class Ledger { }

// main.mjs
import Ledger, { TAX, net as netAmount } from "./math.mjs";
import * as math from "./math.mjs";
console.log(net === math.net, TAX);
```

Rules: named exports are imported by their name in braces; a default export without braces under any name; paths are relative (`./`) or a module specifier a loader resolves. A module executes once, on first import, and every importer shares its exports (live bindings). Imports are hoisted: they are evaluated before the code in the file.

Odoo has its own module loader. In the web client you do not write relative paths between modules; you import by module name:

```js
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { LibraryCard } from "@library/components/card/card";
```

`@odoo/owl` is the OWL library, `@web/...` is the `web` addon's `static/src` folder, and `@library/...` is your own module's `static/src`. The file path inside the addon's `static/src` becomes the module name.

{% hint style="info" %}
Versions: in Odoo 16 and 17, a JavaScript file in an asset bundle is recognised as an ES module only if its first line is the comment `/** @odoo-module **/`. Later versions relax this for files that use `import`/`export`; verify on your build, and note that keeping the annotation is always harmless. If a new file seems not to load in 16 or 17, a missing annotation is the first thing to check.
{% endhint %}

Node does not know Odoo's `@web/...` specifiers, so your own pure-logic helper files (formatting, calculations) are best written without importing from `@web` so you can test them with `node` directly.

## Date, numbers, JSON

```js
const d = new Date("2025-03-01T10:00:00Z");
console.log(d.toISOString(), d.getTime(), d.getUTCFullYear());
console.log(JSON.stringify({ d: new Date(0), u: undefined, n: null }));
// {"d":"1970-01-01T00:00:00.000Z","n":null}
console.log(JSON.parse('{"a":[1,2,{"b":null}]}').a[2].b);  // null
console.log(Number("12.5"), parseInt("12px", 10), (1234.5).toFixed(1), Number.isInteger(2));
console.log(Number("abc"), Number(""), Number(null));        // NaN 0 0
```

`new Date("2025-03-01")` (date only) parses as UTC midnight, while `new Date("2025-03-01T00:00")` (no zone) parses as local time. Odoo stores datetimes in UTC and transmits them as `"YYYY-MM-DD HH:MM:SS"` strings, which are not ISO and must be converted by the framework's helpers (a `luxon` `DateTime` in recent versions) rather than `new Date(string)`. Treat all date conversions as "use the framework helper" in Odoo code.

## What OWL component code looks like

You have now seen every language feature that an OWL component uses. A fragment of a component for a library card, written for Odoo 17/18 style (this is a fragment: it needs the template and an asset bundle to run, covered in the frontend part):

```js
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LoanCounter extends Component {
  static template = "library.LoanCounter";
  static props = {
    bookId: Number,
    label: { type: String, optional: true },
  };

  setup() {
    this.orm = useService("orm");
    this.state = useState({ count: 0, loading: false });
  }

  async refresh() {
    this.state.loading = true;
    try {
      this.state.count = await this.orm.searchCount("library.loan", [
        ["book_id", "=", this.props.bookId],
      ]);
    } finally {
      this.state.loading = false;
    }
  }
}

registry.category("actions").add("library.loan_counter", LoanCounter);
```

Map each line to this chapter: `import` from a named module; `class ... extends` with `static` fields; `setup()` instead of a constructor (the framework calls it); a destructuring-free options object for props; `this.state` as reactive object where assignment triggers a re-render; `async`/`await` with `try/finally` for the request; the `registry` call at the bottom registering the component under a key. The matching template is XML with `t-` directives, and the next chapter covers `async`/`await` and the DOM.

You can feel what `useState` does with a tiny model, runnable in Node. A `Proxy` intercepts assignments, and the framework re-renders when it sees one:

```js
function reactive(target, onChange) {
  return new Proxy(target, {
    set(obj, key, value) {
      obj[key] = value;
      onChange(key, value);
      return true;
    },
  });
}
const state = reactive({ count: 0 }, (k, v) => console.log("render", k, v));
state.count++;       // render count 1
state.count += 2;    // render count 3
```

OWL's `useState` is built on the same idea, with batching and dependency tracking. The practical rules follow from it: mutate state through the reactive object, replace values rather than keeping a separate reference to a plain object you created before wrapping, and do not expect changes to non-reactive fields to re-render anything.

{% hint style="info" %}
Versions: The component style shown here targets Odoo 17 and 18. Odoo 16 also uses OWL 2 but some helpers, hooks, and service access differ between releases. Check the target version's source for any hook you rely on.
{% endhint %}

## Tooling

- Run snippets: `node file.mjs`. For quick experiments, `node` opens a REPL; paste code and see results.
- The browser console (`F12`) runs modern JavaScript too; in Odoo, developer mode adds an asset debugging option that loads unminified code, which makes stack traces readable.
- A formatter and a linter save time: Prettier formats, ESLint finds undefined variables and unused imports. Odoo's own repository uses ESLint with a project config; copy its habits (double quotes, semicolons, 4-space indentation, `const`).
- Check syntax without running: `node --check file.mjs`.

## Pitfalls

- **`this` lost when passing a method as a callback.** `setTimeout(obj.method)` calls it detached. Use an arrow wrapper, a bound class field, or `.bind`.
- **Arrow functions as object methods.** `{ f: () => this.x }` uses the outer `this`, not the object.
- **`==` and truthiness.** Use `===`; test emptiness of arrays explicitly (`list.length`), and use `??` when `0` or `""` are valid.
- **`sort()` without a comparator** sorts numbers as strings.
- **`map(parseInt)`** passes the index as the radix.
- **`for...in` on arrays** and mutating an array while iterating it.
- **Shallow copies.** `{ ...obj }` and `slice()` share nested objects; mutating them changes the original. Prefer `structuredClone` for real copies.
- **Mutating props or state you do not own.** In frameworks with reactivity, mutate only state you created; treat props as read-only.
- **Floating-point money.** `0.1 + 0.2 !== 0.3`. Let the server round, or work in integer minor units.
- **`new Date(string)` guessing.** Different formats parse as different time zones. Use the framework's date helpers for Odoo's string format.
- **Forgetting `await`.** A promise is truthy; `if (check())` on an async function always passes. The next chapter covers it.
- **Unhandled `undefined`.** `a.b.c` throws if `b` is missing. Use `?.` where absence is legitimate, and let it throw where absence is a bug.
- **Missing the module annotation in Odoo 16/17**, which results in a file that is bundled but whose `import` lines fail with a syntax error in the browser console.

## Try it

**1. Closure.** Write `makeLimiter(max)` returning a function that returns `true` the first `max` times it is called and `false` afterwards.

<details>
<summary>Solution</summary>

```js
function makeLimiter(max) {
  let calls = 0;
  return () => calls++ < max;
}
const lim = makeLimiter(2);
console.log(lim(), lim(), lim());   // true true false
```

`calls` lives in the closure; each limiter has its own counter.
</details>

**2. `this`.** Why does this code throw, and give two fixes?

```js
class Btn {
  label = "Save";
  onClick() { return this.label; }
}
const { onClick } = new Btn();
onClick();
```

<details>
<summary>Solution</summary>

`onClick` is detached from the instance, so `this` is `undefined` in module code and `this.label` throws a `TypeError`. Fix 1: define the handler as a class field arrow, `onClick = () => this.label;`. Fix 2: bind at the point of use, `const b = new Btn(); const f = b.onClick.bind(b);` or call it as `b.onClick()`.
</details>

**3. Array pipeline.** Given the `loans` array above, produce an object with the total days per member, for loans of 5 days or more, using one `reduce` and one `filter`.

<details>
<summary>Solution</summary>

```js
const totals = loans
  .filter((l) => l.days >= 5)
  .reduce((acc, { member, days }) => ({ ...acc, [member]: (acc[member] ?? 0) + days }), {});
console.log(totals);   // { Bob: 10, Ann: 7 }
```
</details>

**4. Destructuring.** Write a function `describe` taking one argument shaped like `{ title, meta: { pages = 100, tags: [firstTag = "none"] = [] } = {} }` and returning `"title: pages, firstTag"`. What does `describe({ title: "Dune" })` return?

<details>
<summary>Solution</summary>

```js
const describe = ({ title, meta: { pages = 100, tags: [firstTag = "none"] = [] } = {} }) =>
  `${title}: ${pages}, ${firstTag}`;
console.log(describe({ title: "Dune" }));   // Dune: 100, none
```

Each default applies when its part is `undefined`: `meta` missing gives `{}`, `tags` missing gives `[]`, and `firstTag` missing gives `"none"`.
</details>

**5. Reactive helper.** Extend the `reactive` function so `onChange` is not called when the new value equals the old one.

<details>
<summary>Solution</summary>

```js
function reactive(target, onChange) {
  return new Proxy(target, {
    set(obj, key, value) {
      const changed = obj[key] !== value;
      obj[key] = value;
      if (changed) onChange(key, value);
      return true;
    },
  });
}
const s = reactive({ n: 1 }, (k, v) => console.log("render", k, v));
s.n = 1;   // nothing
s.n = 2;   // render n 2
```
</details>
