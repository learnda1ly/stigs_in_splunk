import { createGlobalStyle } from "styled-components";

export const VimGlobalStyle = createGlobalStyle`
  .stig-vim-wrap {
    position: relative;
    overflow: hidden;
    width: 100%;
    background: #fff;
  }
  .stig-vim-wrap textarea {
    display: block;
    position: relative;
    z-index: 1;
    background-color: transparent !important;
  }
  .stig-vim-measure {
    position: absolute;
    left: 0;
    top: 0;
    visibility: hidden;
    pointer-events: none;
    z-index: -1;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow: hidden;
  }
  .stig-vim-line {
    position: absolute;
    display: none;
    pointer-events: none;
    z-index: 0;
    left: 0;
    background: #d4e8f7;
  }
  .stig-vim-line.is-visible {
    display: block;
  }
  .stig-vim-cursor {
    position: absolute;
    display: none;
    pointer-events: none;
    box-sizing: border-box;
    background: #2b6cb0;
    z-index: 0;
    min-width: 0.7em;
  }
  .stig-vim-cursor.is-visible {
    display: block;
  }
`;
