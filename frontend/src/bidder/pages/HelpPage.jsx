import { Card, PageHeader, Section } from "../../ui/primitives";

const FAQ = [
  {
    q: "How is my compliance checked?",
    a: "When you upload a document (PAN, GST, etc.), the system reads the identifier from it and checks it against the relevant government registry where one is available live. Every result — PASS, FAIL, PARTIAL or UNKNOWN — is traceable back to the document, page and authority that produced it.",
  },
  {
    q: "Does winning an auction mean I've won the tender?",
    a: "No. This system does not run a live auction. Even where a tender includes bidding elsewhere, the auction ending is separate from the procurement award — the procurement officer's compliance and evidence review always comes first, and their recorded decision is what determines the result.",
  },
  {
    q: "Why can't I see other bidders' documents or scores?",
    a: "Bidder identities and evaluation details are confidential between each bidder and the procurement officer. This portal never exposes another bidder's identity, risk assessment or documents.",
  },
  {
    q: "Why does a page say a feature 'requires a backend integration'?",
    a: "This portal only ever shows real data or clearly labels what still needs to be built. Some features — accounts, email/mobile verification, notifications, live auctions — don't have a backend yet, so instead of faking them, the page says so plainly.",
  },
];

export default function HelpPage() {
  return (
    <div className="page page-narrow" style={{ maxWidth: 720 }}>
      <PageHeader eyebrow="Bidder Portal" title="Help" subtitle="How this portal works." />
      <Section title="Frequently asked questions">
        <div className="stack" style={{ gap: 12 }}>
          {FAQ.map((item) => (
            <Card key={item.q} title={item.q}>
              <p className="text-sm text-secondary">{item.a}</p>
            </Card>
          ))}
        </div>
      </Section>
    </div>
  );
}
