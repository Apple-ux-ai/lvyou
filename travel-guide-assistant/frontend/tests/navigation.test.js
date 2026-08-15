import fs from "node:fs";
import path from "node:path";

const projectRoot = process.cwd();
const pagesRoot = path.join(projectRoot, "pages");
const readPage = (name) => fs.readFileSync(path.join(pagesRoot, name), "utf8");

test("main navigation keeps the community entry on every content page", () => {
  expect(readPage("home.html")).toContain('{ id: "community", label: "社区", href: "community.html" }');
  for (const page of ["guides.html", "explore.html", "profile.html"]) {
    expect(readPage(page)).toContain('href="community.html"');
  }
  expect(readPage("community.html")).toContain('"community.html"');
});

test("home page does not expose placeholder links", () => {
  expect(readPage("home.html")).not.toContain('href="#"');
});

test("community page links back into the product flow", () => {
  const source = readPage("community.html");
  for (const href of ["home.html", "explore.html", "guides.html", "community.html"]) expect(source).toContain(`"${href}"`);
  expect(source).toContain('window.TravelMate.utils.go("auth.html")');
  expect(source).toContain("guide-detail.html");
  expect(source).toContain("assistant.html");
});

test("destination navigation opens the destination directory", () => {
  expect(readPage("home.html")).toContain('{ id: "dest", label: "目的地", href: "explore.html" }');
  expect(readPage("guides.html")).toContain('href="explore.html"');
  expect(readPage("community.html")).toContain('["目的地", "explore.html"]');
});

test("secondary pages load the shared navigation layer", () => {
  for (const page of ["assistant.html", "destination.html", "guide-detail.html", "planner.html", "compare.html", "budget.html", "visa.html", "currency.html"]) {
    expect(readPage(page)).toContain('<script src="../shared/site-nav.js"></script>');
  }
});

test("home page exposes tools and the personal center", () => {
  const source = readPage("home.html");
  expect(source).toContain('className="tool-entry-section"');
  expect(source).toContain('href="planner.html"');
  expect(source).toContain('href="budget.html"');
  expect(source).toContain('href="visa.html"');
  expect(source).toContain('href="currency.html"');
  expect(source).toContain('href="profile.html"');
});

test("home assistant preview opens the real assistant without fake chat controls", () => {
  const source = readPage("home.html");
  expect(source).toContain('<a className="chat-window chat-launcher" href="assistant.html"');
  expect(source).not.toContain("chatConversation");
  expect(source).not.toContain("chat-send");
});

test("authentication page has no placeholder hash links", () => {
  expect(readPage("auth.html")).not.toContain('href="#"');
});

test("interactive view-all controls use real buttons or links", () => {
  for (const page of ["destination.html", "explore.html"]) {
    expect(readPage(page)).not.toMatch(/<a className="view-all" onClick=/);
  }
});
