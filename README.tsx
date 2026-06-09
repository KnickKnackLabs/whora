/** @jsxImportSource jsx-md */

import { execFileSync } from "child_process";
import { existsSync, readFileSync, readdirSync } from "fs";
import { join, resolve } from "path";

import {
  Badge,
  Badges,
  Bold,
  Center,
  Code,
  CodeBlock,
  HR,
  Heading,
  Item,
  LineBreak,
  Link,
  List,
  Paragraph,
  Section,
  Sub,
} from "readme";

const PROJECT = {
  name: "whora",
  oneLine: "Stopwatches and countdowns for shell-shaped work.",
  tagline: "Ask what hour it is, then make the work answer.",
  license: "MIT",
};

const REPO_DIR = resolve(import.meta.dirname);
const TEST_DIR = join(REPO_DIR, "test");

function read(path: string): string {
  return readFileSync(path, "utf8");
}

function walkFiles(dir: string, predicate: (path: string) => boolean): string[] {
  if (!existsSync(dir)) return [];

  const results: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkFiles(full, predicate));
    } else if (predicate(full)) {
      results.push(full);
    }
  }
  return results;
}

function countBatsTests(): number {
  return walkFiles(TEST_DIR, (path) => path.endsWith(".bats"))
    .map(read)
    .join("\n")
    .match(/@test\s+"/g)?.length ?? 0;
}

function countPytestTests(): number {
  const output = execFileSync("uv", ["run", "--locked", "pytest", "--collect-only", "-q"], {
    cwd: REPO_DIR,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return output.split("\n").filter((line) => line.includes("::")).length;
}

function configuredLints(): string[] {
  const miseToml = read(join(REPO_DIR, "mise.toml"));
  const start = miseToml.indexOf("[_.codebase]");
  if (start === -1) return [];

  const lines = miseToml.slice(start).split("\n");
  const block: string[] = [];
  for (const [index, line] of lines.entries()) {
    if (index > 0 && line.startsWith("[")) break;
    block.push(line);
  }

  const list = block.join("\n").match(/lint\s*=\s*\[([\s\S]*?)\]/)?.[1] ?? "";
  return [...list.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
}

const batsTestCount = countBatsTests();
const pytestTestCount = countPytestTests();
const totalTestCount = batsTestCount + pytestTestCount;
const lints = configuredLints();

const readme = (
  <>
    <Center>
      <Heading level={1}>{PROJECT.name}</Heading>

      <Paragraph>
        <Bold>{PROJECT.oneLine}</Bold>
      </Paragraph>

      <Paragraph>{PROJECT.tagline}</Paragraph>

      <Badges>
        <Badge label="shape" value="mise + Python" color="3776AB" logo="python" logoColor="white" />
        <Badge label="tests" value={`${totalTestCount}`} color="brightgreen" href="test/" />
        <Badge label="BATS" value={`${batsTestCount}`} color="brightgreen" href="test/" />
        <Badge label="pytest" value={`${pytestTestCount}`} color="brightgreen" href="test/python/" />
        <Badge label="lints" value={`${lints.length}`} color="blue" />
        <Badge label="README" value="TSX" color="f472b6" />
        <Badge label="License" value={PROJECT.license} color="blue" href="LICENSE" />
      </Badges>
    </Center>

    <LineBreak />

    <Section title="What this is">
      <Paragraph>
        <Code>whora</Code>
        {" is a tiny shell-time tool: named stopwatches, named countdowns, editable labels and tags, JSON output for scripts, and gum-styled dashboards for humans."}
      </Paragraph>

      <Paragraph>
        {"It separates two common needs that agents blur together: a "}
        <Bold>stopwatch</Bold>
        {" counts elapsed time, while a "}
        <Bold>countdown</Bold>
        {" has a duration and can become fired/overdue. Countdown notifications are opt-in, so ordinary countdowns do not leave long-running sleeper processes behind."}
      </Paragraph>
    </Section>

    <Section title="Quick start">
      <CodeBlock lang="bash">{`# Inside this repo while developing:
mise run stopwatch:start --label "PR review" --tag repo=notes
mise run stopwatch
mise run stopwatch:stop --id <id>

mise run countdown:start 10m --id ci-check --label "check CI" --tag pr=123
mise run countdown
mise run countdown:update --id ci-check --tag session=iris
mise run countdown:stop --id ci-check`}</CodeBlock>

      <Paragraph>
        {"When installed as a shiv package, the same task names are intended to be available through "}
        <Code>whora</Code>
        {", for example "}
        <Code>whora countdown:start 5m --label "tea"</Code>
        {"."}
      </Paragraph>
    </Section>

    <Section title="Behavior">
      <List>
        <Item><Bold>No magic default timers.</Bold> Starting without <Code>--id</Code> generates an id; stopping requires an explicit id.</Item>
        <Item><Bold>Metadata stays editable.</Bold> Use <Code>update</Code> tasks to set/clear labels and add/remove tags.</Item>
        <Item><Bold>Silent countdowns by default.</Bold> A countdown is considered fired when its deadline passes. Pass <Code>--notify</Code> only when you want a terminal bell/message.</Item>
        <Item><Bold>Human and machine surfaces are separate.</Bold> Default output uses gum where helpful; <Code>--json</Code> stays plain.</Item>
        <Item><Bold>State is local and simple.</Bold> Whora stores one JSON file per timer under <Code>{'${WHORA_STATE_DIR}'}</Code>, then <Code>{'${XDG_STATE_HOME}/whora'}</Code>, then <Code>~/.local/state/whora</Code>.</Item>
      </List>
    </Section>

    <Section title="Examples">
      <CodeBlock lang="bash">{`# Stopwatch with generated id.
mise run stopwatch:start --label "familiarization" --json
mise run stopwatch --label "familiarization"

# Countdown with a stable id so repeated starts replace the same semantic timer.
mise run countdown:start 1m --id min-check --replace --label "check min"
mise run countdown:status --id min-check --json

# Opt into a terminal notification.
mise run countdown:start 5m --id tea --label "check tea" --notify

# Edit metadata later.
mise run stopwatch:update --id <id> --label "PR review" --tag repo=notes
mise run countdown:update --id min-check --remove-tag session=old --tag session=new`}</CodeBlock>
    </Section>

    <Section title="Validation">
      <CodeBlock lang="bash">{`mise run test
codebase lint "$PWD"
mise exec -- readme build --check
git diff --check`}</CodeBlock>

      <Paragraph>
        {"The current suite has "}
        <Bold>{`${totalTestCount} tests`}</Bold>
        {" ("}
        <Bold>{`${batsTestCount} BATS`}</Bold>
        {" + "}
        <Bold>{`${pytestTestCount} pytest`}</Bold>
        {"). "}
        <Code>mise run test</Code>
        {" runs BATS, Python unit tests, and ruff lint/format checks. The repo also has "}
        <Bold>{`${lints.length} convention lints`}</Bold>
        {" configured."}
      </Paragraph>
    </Section>

    <Center>
      <HR />
      <Sub>
        {"This README was generated from "}
        <Code>README.tsx</Code>
        {" with "}
        <Link href="https://github.com/KnickKnackLabs/readme">KnickKnackLabs/readme</Link>
        {"."}
      </Sub>
    </Center>
  </>
);

console.log(readme);
