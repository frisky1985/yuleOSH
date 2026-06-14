import Link from "next/link";
export function generateStaticParams() { return [{ id: "demo-1" }, { id: "demo-2" }, { id: "demo-3" }]; }
export default function ProjectPage({ params }: { params: { id: string } }) {
  return (<div className="min-h-screen bg-gray-50 p-8"><h1 className="text-2xl font-bold">Project {params.id}</h1></div>);
}
