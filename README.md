# Project 2 - Build a RAG System and Measure It

**CSCI 498E / 598E - Coding with AI Agents**

| | |
|---|---|
| **Weight** | 20% of your final grade |
| **Points** | 150 for this project, plus 50 for a video, both on Canvas |
| **Released** | Tuesday, October 6 (lecture 12) |
| **Due** | Tuesday, October 27, 11:59 pm, one deadline for everything |
| **Work** | Individual; 598E adds a rider (below) |

You hand in three things:

1. A **public GitHub repo** made from this template, whose URL you submit on Canvas.
2. The **work inside it**: three retrievers you built, run files and answers you generated, your own corpus and gold set, `EVAL.md` and `DECISIONS.md` written in your own words, and for 598E a `PREREG.md`.
3. A **5 to 10 minute video**, submitted on Canvas as its own assignment.

---

## What this project is

You build a system that searches a collection of documents and answers questions from what it finds.
Then you measure which search method works best on questions you wrote yourself, and you report what your numbers do and do not let you claim.

The system is not the point; the measurement and the judgment are.
Lecture 12 told you that no retriever wins everywhere, and here you test that claim yourself, on two corpora, with intervals that say how much to trust each difference.

The project has two stages, and one deadline for both.

- **Stage 1: the shared corpus.**
  Everyone works on the same collection, **30 CFR Chapter I**: the federal mine safety and health regulations, one section per file.
  It is public domain, it is a Mines subject, and I hold the answer key.
  You build `dense`, `hybrid` and `rerank` from the code you already wrote in labs 12 and 13, next to the `bm25` baseline that ships in this repo.
  You run all four on 20 practice queries (answers public, so you can score yourself) and 40 test queries (answers private, scored by me), and you answer 12 questions with citations.
- **Stage 2: your own corpus.**
  You choose a collection you are allowed to publish, ingest it, write your own gold set, run the same four systems, run one ablation, and analyze where the best system fails.
- **The cross-corpus question.**
  Did the best system on the shared corpus stay the best on yours, and why or why not?
  Lecture 12's claim becomes something you measured.

I know two stages is more work than one corpus would be.
I chose it for five reasons.
Building a retrieval pipeline and preparing a corpus are different skills, and stage 1 means you are not stuck converting PDFs during the first week.
I have no teaching assistants, so I would rather debug one corpus for everyone than thirty-seven different ones.
The private test queries give the whole class one comparable number, which corpora of your own cannot.
Moving your pipeline to a second corpus shows that it is general and not tuned to the first.
And the comparison between the two is the thing I most want you to take away.

### The four systems

| System | What it is | Who writes it |
|---|---|---|
| `bm25` | BM25 keyword search, the lab-calibrated version from 12 | provided |
| `dense` | embeddings of your choice (the potion or bge model from 12, or another) and a nearest-neighbor search | you |
| `hybrid` | fusion of two systems, for example reciprocal rank fusion of `bm25` and `dense` from 12 | you |
| `rerank` | a `claude -p` listwise reranker over a first-stage top 20, as in lab 13 | you |

A retriever is a module in `p2/retrievers/` with a `build(corpus, cfg)` function that returns an object whose `.search(text, k)` gives a list of `(docid, score)` pairs, and a constant `NEEDS_CLAUDE`.
`p2/retrievers/bm25.py` is a working example, and the three you write ship as stubs that raise `NotImplementedError` and point at the lab file that shows the idea.
You may add more systems, for an ablation or because you are curious.

### What a program checks and what I read

`uv run p2 check` is the check that runs on your laptop and in GitHub's CI on every push.
It runs every system that does not call Claude again and compares the result with the run files you committed, checks the runs of the systems that do call Claude against the traces you committed with them, recomputes the scores and the tables in `EVAL.md`, and checks the format of everything else.
At the end I run the instructor's copy of `p2 check --final` on your repo, so editing the checker in your copy cannot help you.
I score your test run files against the answer key I keep private, and I re-run your retrievers on a few documents I add that you have never seen, to confirm that the run files you committed really come from your code.
The test score goes back to you as feedback.
It counts only as complete and reproducible, so it is there to catch a pipeline that works on the practice queries and nothing else, and there is no leaderboard to tune for.
I read `EVAL.md` and `DECISIONS.md` and watch the video myself, because the judgment in them is what I am grading.

---

## Start here

Every command below runs from the root of your own P2 repo, `work/p2-rag` once you have cloned it, unless it says otherwise, and every `p2` command starts with `uv run`.
Say "In work/p2-rag, run ..." to Claude Code, or run it yourself in a terminal in that folder.

1. Click **Use this template** at the top of this repo, then **Create a new repository**.
2. **Name it `p2-rag-system`** and make it **Public**.
   Public, because I need to read it and because the whole project rests on committing only text you are allowed to publish.
3. Clone it into `work/`, your own space in the course repo: say **"clone my P2 repo into work/p2-rag"** to Claude Code, or in a terminal at the root of the course repo run `gh repo clone <your-github-username>/p2-rag-system work/p2-rag`.
   Git ignores `work/`, so this repo never collides with a course update.
   Keep working in the same Claude Code session and say where the work goes (`work/p2-rag`).
   At the start of every Claude Code session you use for P2, the first one and every one after, ask it to read `work/p2-rag/CLAUDE.md`.
   It is a short orientation for the agent, including the rule to tell you how many Claude calls a command makes before it runs it, and Claude Code loads it only after it reads a file in that folder, so running commands there is not enough.
4. **Install `uv`** if the prep for lecture 12 did not already.
   Check with `uv --version`; if it prints a version number, you are done.
   Otherwise, on macOS or Linux run `curl -LsSf https://astral.sh/uv/install.sh | sh`, and on Windows, in PowerShell, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`, then open a new terminal (on Windows, Git Bash) so it is on your PATH.
5. Run `uv sync`.
   It installs the right Python and every package this repo needs, which takes a minute or two the first time.
6. Download the two embedding models by running the lab 12 warm-up once more.
   This one command runs from the root of the course repo, the folder you start Claude Code in, and not from `work/p2-rag`: `uv run class/12-embeddings-and-retrieval/lab/starter/warmup.py`.
   It downloads potion-retrieval-32M and bge-small (about 200 MB) into the Hugging Face cache, which this repo reads too, checks that each one loads, and ends with the word `ready`.
   If you ran it for lecture 12, it finishes in seconds.
   If you skip it, your first `dense` run downloads the same models, so nothing breaks, but you will do it in the middle of your work and not before.
7. Open `p2.toml` and check that `section` matches your course, `"498E"` or `"598E"`.
8. Run `uv run p2 check`.
   On a fresh copy it prints `PASS` lines and `TODO` lines and exits cleanly: a `TODO` line is work you have not done yet and is not an error, and only a `FAIL` line means something is broken.
   Later you may also see `NOTE` lines, which point at something in your gold set worth a second look and never fail the check.
9. Commit and push, open the **Actions** tab of your repo, and wait for the `p2-check` run to go green.
   This first run takes a minute or two, because there is nothing to regenerate yet.
   Once you commit runs of `dense` or `hybrid`, the next run downloads the embedding model and encodes the corpus, which can take several minutes, and later runs reuse a cache.

Please do all of this on the first day, before you have started anything real.
The setup is the step with the most ways to go wrong, and you want it behind you while there is plenty of time.

### A pace that works

There are no checkpoints, and nothing is checked on these dates.
This is the pace I would keep, and I am saying it because the two slow parts of this project, reviewing licenses and judging documents by reading them, are the ones people leave to the last weekend.

- **By lecture 13 (Thu Oct 8):** setup done and CI green, `dense` and `hybrid` working on the practice queries.
- **By lecture 14 (Thu Oct 15):** stage 1 finished, with the reranker, the scores, and the cited answers; your own corpus chosen and its first `p2 license` run done, so you know the corpus is usable.
- **By Tue Oct 20:** the corpus ingested and the gold set written, using what lecture 14 teaches about gold sets.
  598E: `PREREG.md` committed before any judgment goes into your `qrels.txt`.
- **By Fri Oct 23:** the four systems on your corpus, scored, and the ablation done.
- **The last weekend:** failure analysis, cross-corpus comparison, `DECISIONS.md`, the video, and `uv run p2 check --final` on Monday.

Tue Oct 13 is Fall Break, so there is no class, and nothing is due.

---

## Stage 1: the shared corpus

### What is in the repo

- `corpora/shared/docs/` holds 30 CFR Chapter I from the eCFR, one section per file: `cfr30-75.403.md` is section 75.403, with its section number and heading as the first line.
  `NOTICE.md` pins the date of the eCFR copy, explains why it is public domain, and says what it is not: it is not an official legal edition, and nothing here is legal or compliance advice.
  `manifest.tsv` records each document's source and license.
- `eval/shared/practice.queries.tsv` and `practice.qrels.txt` hold the 20 practice queries (7 `identifier`, 7 `paraphrase`, 6 `mixed`, the same three classes as lab 12) and their judgments.
- `eval/shared/test.queries.tsv` holds the 40 test queries (13, 14 and 13).
  Their judgments are not in this repo.
- `eval/shared/questions.tsv` holds the 12 questions for the cited answers: 8 the corpus answers and 4 it does not.

A section is relevant to a query if it states the requirement the query asks about.
When the query does not name a kind of mine, the parallel sections in parts 56 (surface metal and nonmetal), 57 (underground metal and nonmetal), 75 (underground coal) and 77 (surface coal) are all relevant, because the same rule is written once for each.
A section that only cross-references the requirement is not relevant.
That one rule explains most of the surprises you will find when you read a failed query.

### Steps

1. **Read before you build.**
   Open three sections, `NOTICE.md`, five practice queries and their judgments.
   Notice how short the sections are, how often the same rule repeats across parts 56, 57, 75 and 77, and how little of a paraphrase query's wording appears in the section it wants.
   That last point is deliberate: `bm25` finds none of the seven practice paraphrase queries' answers in its top 10, which is what keyword search does when the words differ, not a bug in your setup.
2. **Run the baseline.**
   Say "In work/p2-rag, run `uv run p2 run --corpus shared --queries practice --system bm25`".
   It writes `runs/shared/bm25.practice.trec`; open it and look at the first lines.
   A query that shares words with fewer than ten sections, such as p01, ends with sections that score 0.000000 in document id order: that is padding up to ten lines, not a match.
3. **Build `dense`.**
   Ask Claude Code to read `class/12-embeddings-and-retrieval/lab/starter/retrieve.py` in the course repo and port the embedding arm into `p2/retrievers/dense.py`, using the helpers in `p2/embed.py`.
   The docstring of `p2/retrievers/__init__.py` explains the interface, including the `ChunkScorer` helper that gives you both document search and the chunk search that `p2 answer` needs, and `bm25.py` is the worked example.
   You choose the embedder, and the choice goes in `EVAL.md`.
   If you want a setting of your own, such as the model name, add a table to `p2.toml` (for example `[dense]` with `model = "..."`) and read it in your retriever with `cfg.table("dense")`.
   Run it the same way as the baseline with `--system dense`.
   Scale is the new problem: the lab had 260 articles and this corpus has thousands of sections, so the first run takes a few minutes while the vectors are computed, with a progress line every 15 seconds or so, and then they are cached in `.cache/vectors/`.
   Chunk settings live in `p2.toml`; a section is usually shorter than one chunk, but a few are long.
   A run is always at the document level: the best chunk's score becomes the document's score.
4. **Build `hybrid`.**
   Port the fusion from lab 12 or 13 (`class/13-rag-pipeline/lab/starter/pipeline.py`) into `p2/retrievers/hybrid.py`.
   You decide which two systems to fuse; `bm25` and `dense` is the usual choice, and `dense` with a second embedder is also fair.
5. **Build `rerank`.**
   Port the listwise reranker from lab 13 into `p2/retrievers/rerank.py`: a first-stage top 20, sent to Claude through `p2.claude.call`, which handles the full path, the JSON schema, the model, the saved replies, and the environment for you.
   Keep `NEEDS_CLAUDE = True` in that file, because `p2 check` runs every system again with Claude switched off, and it must not spend your plan doing so.
   It checks a reranker's runs against the trace that `p2 run` writes next to them in `traces/` instead, so commit the trace with the run file.
   Try it on two queries before the full run, because every call draws on your own plan (see the cost note below).
   To do that, copy two lines of `eval/shared/practice.queries.tsv` into `.cache/two.tsv` and run `uv run p2 run --corpus shared --queries .cache/two.tsv --system rerank`, which writes its run file to `.cache/extra/` and leaves `runs/` alone.
   Before any command that makes more than 5 Claude calls, `p2` stops and says how many: in a terminal it asks you, and when Claude Code runs it, it stops until the command is run again with `--yes`, so the agent has to bring the number to you first.
   Until a retriever is written it raises `NotImplementedError`, and `p2 run --all` skips it and lists it as work to do.
6. **Run everything.**
   Say "In work/p2-rag, run `uv run p2 run --all --with-claude`".
   It runs the four systems on the practice and test queries, 60 reranker calls in all, so it asks first; without `--with-claude` it skips the reranker.
   Commit the run files in `runs/shared/`.
7. **Score.**
   Say "In work/p2-rag, run `uv run p2 score`".
   It computes recall@10, MRR@10 and nDCG@10 for every run that has an answer key, per query class, plus the paired intervals and the minimum detectable difference for every pair of systems.
   Recall@10 is the share of a query's relevant documents that are in its top 10, and MRR@10 is 1 divided by the rank of the first relevant one (0 if none is in the top 10), both from lab 12.
   nDCG@10 adds up the relevant documents in the top 10, each divided by log2 of its rank plus 1 so a lower rank counts less, and divides that by the same sum for the best possible order, so 1.0 is a perfect ranking.
   A paired interval is the 95% range of the mean difference between two systems on the same queries, found by resampling the queries 10,000 times; lecture 14 covers both in depth.
   It writes `results/results.json` and fills the tables in `EVAL.md`.
   You then write what the intervals let you claim, in `EVAL.md` section 1.
8. **Answer the 12 questions.**
   Choose a system, and say why in `EVAL.md`.
   `prompts/answer.txt` is the starting prompt from lab 13, and you may edit it.
   Try two questions first, one the corpus answers and one it does not (the ids are in `eval/shared/questions.tsv`): `uv run p2 answer --corpus shared --system rerank --label rerank --only a01,a09`.
   Then run all twelve with the same command without `--only`, which writes `answers/shared/rerank.json`.
   Answering with `rerank` reranks each question before it answers, so it makes two Claude calls per question, 24 for all twelve; answering with `hybrid` makes one, and `p2` counts the replies it already has from your trial.
9. **Verify the answers.**
   Say "In work/p2-rag, run `uv run p2 verify answers/shared/rerank.json`".
   It prints a PASS or FAIL line per question and always finishes cleanly, because a FAIL here is a result to report, not a broken file.
   It checks that every citation is one of the chunks that was retrieved, that every quote appears in the chunk it cites (after lower-casing and collapsing whitespace), that the 4 unanswerable questions were declined with no claims, and that the 8 answerable ones were not.
   The check proves a quote is real.
   It cannot prove that the quote supports the claim next to it, so read three answers yourself and say so in `EVAL.md`.
   Claude may already know these regulations from training, which is why the answer must quote what you gave it, and why the four unanswerable questions are the real test.
10. **Run `uv run p2 check`**, commit, push, and check that CI is green.

### What the Claude calls cost

Anything that runs `claude -p` draws on your own Claude plan.
On this corpus, the course's own versions read about 12,000 input tokens per rerank call and about 7,000 per answer call, a little more than in the 13 lab because the sections are longer than the lab's articles; plan on that much.
A full pass of the reranker over the 20 practice queries, the 40 test queries and your own 30 or more is about 90 calls, roughly a million input tokens.
The 12 answers add about 80,000 input tokens when you answer with `hybrid`, and about 230,000 with `rerank`, which reranks each question before it answers.
That is about three times the 13 lab.
Spread it over several days and try a few queries before every full run.
`p2` saves every Claude reply in `.cache/`, so running the same thing again costs nothing, but a change to your prompt, your candidates or the model asks Claude again, and so do `--fresh` and `--repeat`.
If you reach your usage limit, `/usage` shows where you stand and it resets on its own schedule; the run files you already committed are what count.

---

## Stage 2: your own corpus

### Choose a corpus you may publish

Your corpus goes in a public repo, and CI re-runs retrieval on it.
So it has to be text you may republish, and I do not allow private corpora in this project, not even the pattern of keeping PDFs on your laptop and committing only a manifest.
I know that costs some of you the corpus you would most like to use, because many fields keep their documents behind publisher licenses.
The reason is that CI and I cannot check retrieval on documents we cannot see.
If your field's documents are copyrighted, pick an openly licensed slice of the field.

**Allowed**, each with its license in the manifest:

- Your own writing, entirely yours: reports, notes, essays, code documentation (`own-work`).
- US federal government works (`us-gov-public-domain`), except contractor-written reports and the third-party material that appears inside government reports.
- CC0, CC BY and CC BY-SA text, including Wikipedia (CC BY-SA 4.0, with attribution) and open-access articles whose own license is one of those.
- US public-domain books.
- Openly licensed software documentation (MIT, Apache 2.0, BSD, CC BY), such as Kubernetes.
- PubMed Central open-access articles whose per-article license is CC0, CC BY or CC BY-SA, and arXiv papers under CC0, CC BY or CC BY-SA (arXiv abstracts are CC0).

**Not allowed:**

- Publisher PDFs, textbooks, and engineering standards (ASTM, ISO, IEEE).
- Other courses' materials, and employer or internship documents.
- An advisor's unpublished data, unless you have their written permission.
- Anything with other people's personal data, and anything export-controlled.
- Anything licensed NC (non-commercial) or ND (no derivatives), because whether chunks and embeddings count as adaptations has no settled answer.
- Anything with no license at all: a missing copyright notice does not make a work free.

I am not telling you that using copyrighted text in a retrieval system is safe.
Whether it is fair use depends on the facts, and recent court decisions have gone against at least one company that did it.
I am not a lawyer, and this is not legal advice.
The rule for this project is simpler and stricter: commit only text you can show you may republish.

If you have no corpus of your own, choose from this short list:

- **OSHA's rules, 29 CFR parts 1910 and 1926**, public domain, from the eCFR.
  Take a slice, such as one part or a few subparts, because the two parts together are about 1.2 million words, over the size guidance below.
  This text is the same kind as the shared corpus, so your cross-corpus comparison will be less interesting than for a different kind of text.
- **The USGS Mineral Commodity Summaries**, public domain as federal works, with one catch: the front matter of each volume says permission must be secured from the individual copyright owners for any copyrighted material inside it, such as a photo credited to a company.
  The license tool flags that sentence only where it appears, in the volume's first pages, and the per-commodity chapter PDFs, the easy way to reach 200 documents, do not repeat it.
  So a corpus of chapters can come back clean, and you still say in `EVAL.md` that the volume makes this reservation and why your chapters are text you may publish.
  Ingest each year's chapters with its own `--source`, for example `--source "https://pubs.usgs.gov/periodicals/mcs2024/{name}"`, so every document records the address of its own file.

The eCFR's website blocks scripts but its API does not, so ask Claude Code to write a small fetch script (I fetched 30 CFR that way).
Keep your raw downloads outside the repo, for example in `work/p2-raw/`, which from inside `work/p2-rag`, where every command runs, is `../p2-raw`.

Size rules, checked by `p2 check`:

- At least **200 documents** from one domain.
  Below that, every system finds nearly everything and the comparison measures nothing.
  Long documents split into parts of about 10 pages, and each part counts as a document.
- At most **25 MB** under `corpora/own/` and 10 MB per file, and at most about **500,000 tokens** (words times 1.4), because CI encodes the whole corpus cold and has 30 minutes to do it: `p2 check` warns above 500,000 and fails above 600,000.
- Between 500 and 1,500 documents is a good size, as long as the corpus stays under the token limit, which for long documents means fewer of them; past about 1,500 you add CI time and not information.

### Steps

1. **Ingest it.**
   Install the converters with `uv sync --group ingest`, which CI never does, and run `uv run p2 ingest ../p2-raw --into own --license <id> --source "<where it came from>"`, where `<id>` is one of the license values listed in step 3.
   In `--source`, `{name}` stands for each file's name, so `--source "https://example.org/reports/{name}"` gives every document the address of its own file.
   PDFs go through pypdf, web pages through trafilatura, and `.md` and `.txt` files are read as they are.
   Word and PowerPoint files are refused, and the message tells you to export them to PDF first.
   Ingest runs a cleaning pass that strips markup, repairs ligatures and soft hyphens, re-joins words hyphenated across lines, drops page headers and footers, and drops a trailing reference list.
   This matters because raw converter output breaks the quote check on 8% to 41% of sentences in my tests, and cleaned text breaks it on 1% or less.
   Documents over about 15,000 words are split into parts with the page range in the id, and exact duplicates are skipped.
   If your documents have different licenses, run ingest once per license so each batch gets its own `--license` and `--source`, or edit the manifest rows by hand.
   Document ids come from file names and never change once your judgments mention them.
   Titles come from the PDF's metadata, the first heading or the first line; when several PDFs share one metadata title, as every chapter of a volume often does, each title starts with its file name instead.
2. **Read `corpora/own/INGEST.md`.**
   It has one line per document with its word count, characters per page and any flags.
   A document with fewer than about 400 characters per page is probably a scanned image with no text; drop it, or ask Claude Code about the OCR option in the ingest docs.
   Open three documents and read them, because a corpus you have not looked at will surprise you later.
   If you remove documents by hand later, `uv run p2 ingest --report` rewrites `INGEST.md` for the documents that are left.
3. **Check the licenses.**
   Run `uv run p2 license`.
   It writes `LICENSES.md` and fails when a document's `license` in the manifest is not on the allowed list: `us-gov-public-domain`, `public-domain`, `cc0-1.0`, `cc-by-2.0` to `cc-by-4.0`, `cc-by-sa-2.0` to `cc-by-sa-4.0`, `own-work`, `mit`, `apache-2.0`, `bsd-2-clause` and `bsd-3-clause`.
   Anything else fails, including `unknown`, an empty value, and anything NC or ND.
   It also scans each document's text for a copyright line, "All rights reserved", a publisher's name next to words about rights (such as "Published by Elsevier"), a CC BY-NC notice, "reprinted with permission", the USGS permission sentence, a contractor's notice and a "courtesy of" credit line.
   Each hit is a flag, and a flag passes only when the manifest's `notes` column says `reviewed: <reason>` for that document.
   A publisher's name on its own, such as "see ASTM E2500", is usually a citation, so `LICENSES.md` lists it as a mention and it needs no review.
   Ask Claude Code to "read `work/p2-rag/.claude/skills/license-check/SKILL.md` and walk me through my license failures", and it takes you through each failing or flagged document: it opens the source page, finds and quotes the license text, and you decide whether to record `reviewed: <reason with the quote>` or remove the document.
   Run `uv run p2 license --online` on your own machine as well; for a source with a DOI, an arXiv id or a PubMed Central id, it asks Crossref, arXiv or PubMed Central for the published license and reports any mismatch with yours.
   The tool gathers evidence and flags problems.
   It cannot prove a license, and you remain responsible for what you commit, so when you cannot quote the license for a document, take the document out.
4. **Write your gold set.**
   `eval/own/queries.tsv` has one query per line: `qid`, `class`, `text`, `origin`, separated by tabs.
   `eval/own/qrels.txt` has one judgment per line, `qid 0 docid 1`.
   - At least **30 queries**, at least **10 with `origin` `hand`**, and every query with at least one relevant document.
   - `hand` means you wrote the query yourself, from your own question or from reading the corpus.
     `claude` means a model drafted it, which is allowed for the rest, and you still judge relevance.
     The column exists so you can check whether the queries a model wrote favor the keyword systems, which they often do because they copy the document's own words.
   - The `class` is a free word.
     The shared sets use `identifier`, `paraphrase` and `mixed`; use those or classes that fit your corpus, because per-class scores are reported.
   - Judge relevance by reading each document, and write your rule in `EVAL.md`.
     Find candidates from several places: the top 10 of more than one system, a keyword search, and your own reading.
     A gold set built only from what one system returned is biased toward that system.
   - Claude Code can search the corpus for candidates, and it can draft queries, but you decide what is relevant.
5. **Run the four systems.**
   Say "In work/p2-rag, run `uv run p2 run --all --with-claude`", which writes `runs/own/<system>.trec` for each system and asks before the reranker's calls.
6. **Score.**
   Run `uv run p2 score` again, and the own-corpus tables in `EVAL.md` fill in.
7. **Run one ablation.**
   An ablation changes one thing and keeps everything else the same, so you can say what that one thing did.
   Good candidates: the chunk size, the BM25 tokenizer (`tokenizer = "lab"` gives lab 12's simple one), a second embedding model, how many candidates the reranker sees, the fusion method.
   Write your hypothesis in `EVAL.md` before you run it.
   Make the variant its own system by adding a file to `p2/retrievers/`, for example `bm25_lab.py` or `dense_potion.py`; a file there is a system, and nothing else needs registering.
   A variant that only changes a setting can build with a changed copy of the settings, `cfg.replace(chunk_words=100)`, so you do not have to edit `p2.toml`, which every system shares.
   Run it with `--ablation`, as in `uv run p2 run --corpus own --system bm25_lab --ablation`, which writes the run file to `runs/own/ablation/`.
   From then on `p2 run --all` runs it again only as that ablation, not on every query set.
   Then run `uv run p2 score` and write what the interval lets you claim; the `own-ablation` table in `EVAL.md` compares it with your other systems.
8. **Write the analysis** (next section), then `uv run p2 check --final`.

---

## The analysis

### The failure analysis

Take the queries where your best system on your own corpus fell short, at least five, and read what it returned next to what was relevant.
Sort them by cause: the vocabulary of the query and the document differ, near-duplicate documents compete, a chunk cut the answer in half, the query was ambiguous, or the label was wrong.
The last one happens more than you would think, and finding it is a good result.
Then say what you would try, and what evidence would tell you whether it worked.
`EVAL.md` section 6 has a table for it.

### The cross-corpus comparison

Put the systems side by side on the two corpora, using the tables `p2 score` wrote.
Say whether the winner changed, and then explain why, using what you know about the two collections: how long the documents are, how much of their vocabulary is shared with the queries, whether identifiers matter, whether near-duplicates are common.
Say which explanations you tested and which are guesses.

### What "not distinguishable" means

With about 30 queries, many differences between systems are too small for your gold set to see.
For every pair of systems, `p2 score` gives the mean difference and its paired interval, which is the 95% range of that difference when the queries are resampled 10,000 times.
If the interval includes zero, you cannot say which system is better, and the right words are "not distinguishable on this gold set".
That is a different statement from "the two are equal".
It says the gold set was too small to tell.

`p2 score` also gives the minimum detectable difference, the smallest gap this many queries could reliably show.
If the typical per-query spread is about 0.3, then 30 queries can only detect a difference of about 0.15 in MRR, and a gap of 0.05 is invisible however real it is.
On the shared practice queries the spread between two systems is 0.3 at the smallest and over 0.6 at the largest, so most pairs need more queries than that.
So write the interval, say "not distinguishable" when it includes zero, never rank two systems by their averages alone, and say how large a difference you could have seen.
A claim that matches its interval is a good result even when the answer is "I cannot tell".

---

## The 598E rider

The rider is required for 598E and is one of the stretch options for 498E.
Set `section = "598E"` in `p2.toml`, which makes `p2 check --final` verify the files below.
It has two parts, and I estimate 4 to 6 extra hours, mostly the larger gold set.

**Repeats, on the shared corpus.**
The Claude-based steps are not deterministic, so run them three times, asking Claude again each time.
For the reranker that is `uv run p2 run --corpus shared --queries practice --system rerank --repeat 3`, which saves `runs/shared/rerank.practice.r1.trec`, `.r2.trec` and `.r3.trec`.
For the cited answers it is `uv run p2 answer --corpus shared --system rerank --label rerank --repeat 3`, which saves `answers/shared/rerank.r1.json`, `.r2.json` and `.r3.json`.
`p2 score` reports the run-to-run spread, and Wilson 95% intervals on the share of quotes verified and the share of unanswerable questions correctly declined.
A Wilson interval is a confidence interval for a share that behaves well on small counts: 4 declined out of 4 still leaves an interval from about 0.5 to 1, which is the honest size of what 4 questions can show.
Then say whether the reranker's gain over its first stage survives the run-to-run variation.
The three reranker repeats and the three answer sets add about 130 Claude calls (60 for the reranker, and 72 for the answers, since answering with `rerank` makes two calls per question).

**A pre-registered, powered claim, on your own corpus.**
`PREREG.md` holds your hypothesis, the smallest effect that matters, the gold-set size you need to detect it (computed from the per-query spread you measured in stage 1), and the test.
You commit it before the first judgment appears in `eval/own/qrels.txt`, and `p2 check --final` reads `git log` to confirm the order.
Afterwards you report the outcome against it.
A well-powered null scores as well as a confirmation, so you have no reason to hedge the claim.
Pre-register a smallest effect of at least 0.15 in MRR@10 or nDCG@10, unless you argue for a larger one: a smaller gap is rarely worth a reranker's cost, and detecting it takes more queries than one project can judge.
The gold-set size then follows from the per-query spread you measure in stage 1.
For `rerank` against `hybrid` that spread is about 0.39 on the practice queries, so a gap of 0.15 needs about 55 queries, against the 30 that 498E uses.
Spreads differ by pair, from about 0.31 (`hybrid` against `bm25`) to about 0.66 (`dense` against `bm25`), and at 0.66 even a gap of 0.15 needs about 150 queries, so compare a pair whose spread you can afford, or take a larger gap and say why.
Say in `PREREG.md` how you chose the pair, the gap and the gold-set size.

---

## How the 150 points are planned

This is how I plan to grade.
Canvas is the record, and if I change this table before the deadline I will announce it there.

| Part | Points | What earns it |
|---|---|---|
| Stage 1: the systems | 30 | `dense`, `hybrid` and `rerank` built and run on the shared corpus, run files for the practice and test queries committed and reproducible, CI passing |
| Stage 1: the scores | 10 | the practice scores with paired intervals in `EVAL.md`, and what they let you claim |
| Stage 1: cited answers | 15 | answers to the 12 questions, quotes verified, the 4 unanswerable ones declined |
| Stage 2: your corpus | 10 | at least 200 documents, size rules met, a clean license report |
| Stage 2: your gold set | 15 | at least 30 queries, at least 10 `hand`, each with a relevant document, and your relevance rule written down |
| Stage 2: the four systems | 10 | `bm25`, `dense`, `hybrid` and `rerank` run on your corpus, scored, with intervals |
| Stage 2: one ablation | 10 | one change, a hypothesis written first, a committed run, and a claim that matches the interval |
| Failure analysis | 10 | at least five failures, read and sorted by cause |
| Cross-corpus comparison | 10 | whether the winner changed and a tested or honestly labeled explanation |
| `DECISIONS.md` | 5 | five prompts answered in your own words, with specifics |
| One stretch | 25 | 498E: any one of the options below; 598E: the rider, required |

That is 55 points for stage 1, 45 for stage 2, 25 for the analysis and 25 for the stretch.
The hidden test queries are graded as complete and reproducible only, and their score is feedback.

The stretch options for 498E are the 598E rider; a claim-level faithfulness check with `claude -p` plus a calibration where you check 20 claims by hand; traces from `traces/` opened in Phoenix, an open-source viewer for model traces, with one finding; a second ablation; or the agent-with-grep arm from lab 12 on 10 queries, with its cost.
Name your stretch in `EVAL.md` section 8.

I would rather say this now than have you find out later: without a stretch, the most this project can reach is 125 of 150, and with the video it is 175 of 200.
That is 87.5% on this project, so here an A needs a stretch.
The stretch is worth doing properly and not worth doing in the last hour.

---

## The video

The video is a separate assignment on Canvas, worth 50 points.
Record 5 to 10 minutes, with any tool and any quality; a phone or a screen recording with your voice over it is fine.
Cover three things, in whatever order feels natural:

1. **The project.**
   What you built and what you found: show the repo, one table from `EVAL.md`, and say what the numbers do and do not let you claim.
2. **Your observations.**
   What surprised you, which system won where, and what you would not have guessed from lecture 12.
3. **The challenges and how you solved them.**
   A real one, in your words.
   Where you overruled the agent is a good story to tell here.

I am asking for this because the code and the runs can come from an agent and the video cannot.
It is your voice, your reasons and your story, and that matters more when a model wrote most of the code.
I care about the story and not about production quality.

---

## The deadline

Everything is due **Tuesday, October 27, at 11:59 pm**.
There are no checkpoints, because I would rather you finish the whole thing by the deadline than turn something in halfway.
On Canvas you submit the URL of your repo for the project, and the video as its own assignment.
Push your last commit before you submit.

Late work loses 20%, and nothing is accepted more than a week late.
Canvas is the system of record for the deadline.
If Canvas and this file ever disagree, Canvas wins, and please tell me so I can fix it.

---

## Ground rules

- **Using Claude Code is the point**, not something to disclose or apologize for.
  This is a course about driving agents well.
- **Your repo is public, and so is its history.**
  Do not commit API keys, passwords, personal information, or other people's private documents.
  A secret you delete in a later commit is still readable.
  You never need an API key in this project, because `claude -p` uses your Claude Code sign-in.
- **Commit only text you may publish**, with its license recorded.
- **The numbers must come from your code.**
  Run files, their traces, answers files, `results/results.json` and the tables in `EVAL.md` are written by commands.
  `p2 check` runs your systems again, checks the reranker's runs against their traces, and recomputes the scores and tables, and I also run your retrievers on documents you have not seen and score your test runs.
  Do not edit those files by hand, and do not hard-code answers.
- **Write the judgment parts yourself:** your `hand` queries, your relevance labels, `DECISIONS.md`, the prose in `EVAL.md`, and `PREREG.md`.
  The agent can find candidates and explain numbers.
- **Tune on the practice queries, never on the test queries.**
  You cannot see the test judgments, so the test score is the honest check on whether your pipeline generalizes.
- **What to edit and what not to:** the three retrievers, `prompts/answer.txt`, `p2.toml`, your corpus and gold set, and your own writing are yours.
  The rest of `p2/`, `tests/`, the shared corpus and queries, the workflows, and the license skill belong to the course, and the instructor's copy of the checker is what grades you, so changing yours cannot help.
  `CLAUDE.md` has the exact list.
  If you think one of those files has a bug, tell me; that is a bug too, and I would rather fix it for everyone.

---

## When it breaks

- **CI is red.**
  Run `uv run p2 check` on your own machine, and read the `FAIL` lines; each one says what to do next.
  The usual causes are a committed run that no longer reproduces because you changed your code or `p2.toml` after generating it (run it again and commit the new file), a reranker run committed without its trace in `traces/`, a `results/results.json` or `EVAL.md` table that is out of date (run `uv run p2 score`), a carriage return in a file under `corpora/` (set your editor to LF line endings), and a failing license or a corpus over the size limits.
  A `TODO` line is not a failure.
- **A model download fails or hangs.**
  Check your internet connection and run the warm-up again; files that finished downloading are kept.
  A line about "unauthenticated requests to the HF Hub" is only a notice.
  On a Mac on the Mines network, if every download says "Could not resolve host" while your browser works, iCloud Private Relay is a known cause: in System Settings, open Wi-Fi, Details for the Mines network, and turn off Limit IP Address Tracking.
- **`claude -p` fails or asks you to sign in.**
  Open `claude` once in a terminal and sign in, then run the command again.
  `p2/claude.py` removes `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` from the child process, and prints a line when it does, so a key left over from another course is never billed for your runs.
  If `claude` is not found, check that `claude --version` works in the same terminal.
  On Windows, `p2` refuses a `claude.cmd` from an npm install, because Windows cannot pass a multi-line prompt through it safely; install Claude Code with the official installer from `setup.md` instead.
- **You hit your usage limit.**
  Wait for the reset, do the parts that do not need Claude in the meantime (the corpus, the gold set, the analysis), and spread the Claude steps over more days.
- **Windows or an Intel Mac.**
  The template is written to run on both, and its own tests run on Windows and macOS, but those two are the setups I have tested least.
  On Windows, use Git Bash for every command.
  `uv sync` picks a Python below 3.14 on purpose, because that range keeps Intel Macs working, so leave `.python-version` and the `requires-python` line in `pyproject.toml` alone.
  An Intel Mac needs macOS 13 or newer, because that is the oldest system the embedding library ships for.
  A Windows laptop with an ARM processor (a Snapdragon, say) has no packages of its own for the embedding library, so run `uv sync --python cpython-3.12-windows-x86_64-none` once, which uses the Intel version of Python under Windows' emulation; tell me if it fails.
  If something fails, send me the exact output.
- **The stubs raise `NotImplementedError`.**
  That is expected until you write the retriever; the message names the lab file that shows the idea.

Still stuck after 20 minutes?
Come to office hours: Tue and Thu, 9 to 10 am and 2 to 3 pm, CTLM 246L.
Bring the exact error message, because the words on the screen usually save us half the debugging time.

And if anything in this brief is unclear or seems wrong, tell me.
That is a bug too, and I would rather fix it than have you guess.
