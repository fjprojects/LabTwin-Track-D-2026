export default function SourceLinks({ items = [], onSource }) {
  return <div className="sourceLinks">{items.map(source => <a key={source.id} href={source.href || `#source=${source.id}`} onClick={event => { event.preventDefault(); onSource(source.id); }}>Source: {source.label}</a>)}</div>;
}
