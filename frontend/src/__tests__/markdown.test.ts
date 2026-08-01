/**
 * Regression tests for the XSS-safe markdown renderer (X-01 / S-P2-03).
 *
 * KB article content is user/LLM-authored; a stored payload such as
 * <script>alert(1)</script> or <img src=x onerror=...> must be escaped to
 * inert text (never executed), while normal markdown keeps rendering.
 */

import { escapeHtml, simpleMarkdown } from "@/lib/markdown";

describe("escapeHtml", () => {
  it("escapes HTML metacharacters", () => {
    expect(escapeHtml(`<script>alert(1)</script>`)).toBe(
      "&lt;script&gt;alert(1)&lt;/script&gt;"
    );
  });

  it("escapes quotes and ampersand", () => {
    expect(escapeHtml(`a&b"c'd`)).toBe("a&amp;b&quot;c&#39;d");
  });
});

describe("simpleMarkdown XSS regression (X-01)", () => {
  // DOM-level check: render the output and assert no executable element
  // (img/script/a with js protocol) is actually created by the browser.
  function renderToDom(html: string): HTMLElement {
    const div = document.createElement("div");
    div.innerHTML = html;
    return div;
  }

  it("renders <script> payloads as inert text", () => {
    const out = simpleMarkdown("<script>alert(1)</script>");
    expect(out).not.toContain("<script>");
    expect(out).toContain("&lt;script&gt;");
    expect(renderToDom(out).querySelector("script")).toBeNull();
  });

  it("renders <img onerror> payloads as inert text (no real tag survives)", () => {
    const out = simpleMarkdown('<img src=x onerror=alert(1)>');
    const dom = renderToDom(out);
    // No executable element is created…
    expect(dom.querySelector("img")).toBeNull();
    expect(dom.querySelector("[onerror]")).toBeNull();
    // …the payload is only visible as inert text.
    expect(out).toContain("&lt;img");
    expect(dom.textContent).toContain("onerror=alert(1)");
  });

  it("escapes payloads inside markdown code blocks", () => {
    const out = simpleMarkdown("```js\n<script>alert(1)</script>\n```");
    expect(out).not.toContain("<script>");
    expect(out).toContain("&lt;script&gt;");
    expect(out).toContain("<code");
    expect(renderToDom(out).querySelector("script")).toBeNull();
  });

  it("escapes javascript: URLs inside raw HTML (no real <a> survives)", () => {
    const out = simpleMarkdown('<a href="javascript:alert(1)">x</a>');
    const dom = renderToDom(out);
    expect(dom.querySelector("a")).toBeNull();
    expect(dom.querySelector("[href]")).toBeNull();
    expect(out).toContain("&lt;a");
    expect(dom.textContent).toContain("javascript:alert(1)");
  });
});

describe("simpleMarkdown normal behavior (no regression)", () => {
  it("renders bold", () => {
    expect(simpleMarkdown("**bold**")).toContain("<strong");
    expect(simpleMarkdown("**bold**")).toContain("bold");
  });

  it("renders inline code", () => {
    const out = simpleMarkdown("use `int` here");
    expect(out).toContain("<code");
    expect(out).toContain("int");
  });

  it("renders headers and lists", () => {
    expect(simpleMarkdown("# Title")).toContain("<h1");
    expect(simpleMarkdown("- item")).toContain("<li");
  });

  it("preserves C++-style angle-bracket text", () => {
    const out = simpleMarkdown("use std::vector<int> and std::map<k,v>");
    expect(out).toContain("std::vector&lt;int&gt;");
    expect(out).not.toContain("<script");
  });
});
