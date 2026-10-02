import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BarChart, Donut, LineChart, StatTile } from "./Charts";

describe("charts", () => {
  it("renders bars with a legend for multiple series", () => {
    const { container } = render(<BarChart labels={["a", "b"]} series={[{ name: "One", values: [1, 2] }, { name: "Two", values: [2, 1] }]} />);
    expect(container.querySelectorAll("rect.bar")).toHaveLength(4);
    expect(screen.getByText("One")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /One, Two/ })).toBeInTheDocument();
  });
  it("omits the legend for a single series", () => {
    const { container } = render(<LineChart labels={["0:00", "1:00"]} series={[{ name: "Words", values: [10, 20] }]} />);
    expect(container.querySelector(".chart-legend")).toBeNull();
    expect(container.querySelector("path")).not.toBeNull();
  });
  it("renders donut total and stat tiles", () => {
    render(<Donut items={[{ label: "supported", value: 3 }, { label: "contradicted", value: 1 }]} />);
    expect(screen.getByText("4")).toBeInTheDocument();
    render(<StatTile label="words" value={12} hint="kept" tone="good" />);
    expect(screen.getByText("words · kept")).toBeInTheDocument();
  });
});
