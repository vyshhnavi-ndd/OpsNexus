import React from "react";
export default function Badge({ children }) {
  const value=String(children||"").toUpperCase();
  const tone=["SUCCESS","SUCCEEDED","COMPLETED","TRUSTED","APPROVED","ON TIME"].includes(value)?"success":["FAILED","FAILURE","ERROR","AT RISK","REJECTED","BREACHED"].includes(value)?"danger":["RUNNING","PENDING","IN PROGRESS","REVIEW"].includes(value)?"warning":"neutral";
  return <span className={`badge ${tone}`}><span className="badge-dot"/>{children}</span>;
}
