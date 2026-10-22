export default function SectionTitle({ title, subtitle, action }) {
  return <div className="section-title"><div><h3>{title}</h3>{subtitle&&<p>{subtitle}</p>}</div>{action}</div>;
}
