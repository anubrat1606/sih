import { Card, PageHeader, Section } from "../../ui/primitives";

// Static, plain-language, in the voice of docs/SIMPLE_CHECKLIST.md -- no
// FAQ accordion, no chat widget, just headings and paragraphs. Nothing on
// this page fetches anything; it never goes stale relative to a backend
// change and never needs a loading/error state.
const LIFECYCLE_STEPS = [
  "The procurement office publishes a tender.",
  "You find it in Tenders and review what it requires under the tender's Eligibility tab.",
  "You submit your documents against that tender.",
  "The system reads and checks your documents automatically — this is not a decision, only a record.",
  "The procurement office reviews everything and records a final decision: qualified or not qualified.",
  "You see that decision under My results, with a plain-language reason where one was given.",
];

export default function HelpPage() {
  return (
    <div className="page page-narrow" style={{ maxWidth: 760 }}>
      <PageHeader eyebrow="Bidder Portal" title="Help" subtitle="What this portal is, and how it works." />

      <Section title="What this portal is">
        <p className="text-sm text-secondary">
          This is where you, as a bidder, discover tenders, see exactly what each one requires, submit your
          own compliance documents, and see the procurement office's final decision once it's made. It does
          not decide anything on your behalf — every requirement is checked against your documents, and a
          human officer at the procurement office makes the final call.
        </p>
      </Section>

      <Section title="How a tender moves from published to decided">
        <Card>
          <ol className="stack-sm" style={{ margin: 0, paddingLeft: 20 }}>
            {LIFECYCLE_STEPS.map((step, i) => (
              <li key={i} className="text-sm" style={{ marginBottom: i < LIFECYCLE_STEPS.length - 1 ? 8 : 0 }}>
                {step}
              </li>
            ))}
          </ol>
        </Card>
      </Section>

      <Section title="What &ldquo;documents received&rdquo; means">
        <p className="text-sm text-secondary">
          It means exactly that — your file reached the system and was read. It is not an approval and not
          a sign that you meet a requirement. Compliance is only decided once the procurement office records
          a final decision, which you'll see under My results.
        </p>
      </Section>

      <Section title="What a decision means, and who makes it">
        <p className="text-sm text-secondary">
          A decision — qualified or not qualified — is recorded by a procurement officer after reviewing your
          submission against the tender's published requirements. It is the only thing on this portal that
          counts as a result. Submitting documents, or any automatic check along the way, is never itself a
          result.
        </p>
      </Section>

      <Section title="If a document couldn't be read">
        <p className="text-sm text-secondary">
          When you submit a document, the page tells you immediately if a page couldn't be read. The most
          common real reason is that the file is a scanned image with no underlying text layer — the system
          reads a PDF's actual text, not a picture of text, so a scan needs to be a text-based PDF (or you'll
          need to resubmit one that is) for its contents to be read automatically.
        </p>
      </Section>

      <Section title="Who to contact">
        <p className="text-sm text-secondary">
          For anything about a specific tender's requirements, deadline, or decision, contact the issuing
          authority named on that tender's own page — this portal doesn't have a separate support channel
          beyond the procurement office running the tender you're bidding on.
        </p>
      </Section>
    </div>
  );
}
