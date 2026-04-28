import React from "react";
import { Pagination, Stack, Typography } from "@mui/material";

export function EntreprisesPaginationBar(props: {
  page: number;
  pageCount: number;
  total: number;
  loading: boolean;
  canPrev: boolean;
  canNext: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  const pageOneBased = props.page;
  return (
    <Stack direction={{ xs: "column", md: "row" }} sx={{ alignItems: { xs: "flex-start", md: "center" }, justifyContent: "space-between", mt: 1.25, gap: 1 }}>
      <Typography variant="body2" color="text.secondary">
        Page <strong>{props.page}</strong> / {props.pageCount} (total {props.total})
      </Typography>
      <Pagination
        count={Math.max(1, props.pageCount)}
        page={pageOneBased}
        size="small"
        disabled={props.loading}
        color="primary"
        onChange={(_, value) => {
          if (value > pageOneBased && props.canNext) props.onNext();
          if (value < pageOneBased && props.canPrev) props.onPrev();
        }}
      />
    </Stack>
  );
}

