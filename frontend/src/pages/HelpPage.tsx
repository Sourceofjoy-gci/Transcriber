import type { ReactElement } from "react";

import { PageHeader } from "../components/common";

export function HelpPage(): ReactElement {
  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Reference"
        title="Help"
        subtitle="Troubleshooting notes for users and operators."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <HelpSection
          title="Upload troubleshooting"
          items={[
            "Use supported audio or video formats and keep files below the configured upload limit.",
            "If metadata stays pending, check worker availability and storage health.",
            "Project selection controls retention and external API policy for new media.",
          ]}
        />
        <HelpSection
          title="Transcription review"
          items={[
            "Use transcript versions before bulk edits or AI post-processing.",
            "Speaker labels can be corrected after diarisation completes.",
            "Exports can be generated from full transcripts, selected sections, or reports.",
          ]}
        />
        <HelpSection
          title="Worker operations"
          items={[
            "Model downloads must pass checksum verification before they can run jobs.",
            "Incompatible or disabled local models are blocked before queue execution.",
            "Storage purge respects retention policy and legal holds.",
          ]}
        />
        <HelpSection
          title="Administration"
          items={[
            "Use organisations to separate policy, users, projects, and assets.",
            "Custom roles should grant the smallest permission set needed for a workflow.",
            "External API providers require explicit policy and user acknowledgement.",
          ]}
        />
      </div>
    </section>
  );
}

function HelpSection({
  title,
  items,
}: {
  title: string;
  items: string[];
}): ReactElement {
  return (
    <article className="rounded-2xl border border-emerald-950/10 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <ul className="mt-3 space-y-2 text-sm text-slate-600">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  );
}
