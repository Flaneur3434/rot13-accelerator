/*
 * Copyright (c) 2026 Kendall Carmel
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_flaneur3434_rot13_decoder (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // 50 MHz / 115200 baud = 434 clocks per bit
  localparam CLOCKS_PER_BIT = 434;
  // 16x oversample: 434 / 16 ≈ 27
  localparam OVERSAMPLE_DIV = 27;

  // UART RX input (active low start bit, active high idle)
  wire rx_in = ui_in[0];

  // Synchronizer, adds metastability protection
  reg rx_sync1, rx_sync2;
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rx_sync1 <= 1'b1;
      rx_sync2 <= 1'b1;
    end else begin
      rx_sync1 <= rx_in;
      rx_sync2 <= rx_sync1;
    end
  end
  wire rx = rx_sync2;

  // Sampling tick generator
  reg [4:0] oversample_cnt;
  wire      tick_16x = (oversample_cnt == 0);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      oversample_cnt <= 0;
    else if (oversample_cnt == OVERSAMPLE_DIV - 1)
      oversample_cnt <= 0;
    else
      oversample_cnt <= oversample_cnt + 1;
  end

  // UART RX State Machine
  localparam STATE_IDLE  = 2'd0;
  localparam STATE_START = 2'd1;
  localparam STATE_DATA  = 2'd2;
  localparam STATE_STOP  = 2'd3;

  reg [1:0] state;
  reg [3:0] tick_cnt;     // counts 16x ticks within a bit (0..15)
  reg [2:0] bit_idx;      // which data bit (0..7)
  reg [7:0] rx_shift;     // shift register for incoming byte
  reg       rx_done;      // pulses high for 1 clock when byte received
  reg       rx_idle;      // line was seen high; prevents false start after framing error

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state    <= STATE_IDLE;
      tick_cnt <= 0;
      bit_idx  <= 0;
      rx_shift <= 0;
      rx_done  <= 0;
      rx_idle  <= 1;
    end else begin
      rx_done <= 0; // default: clear strobe

      if (tick_16x) begin
        case (state)
          STATE_IDLE: begin
            if (rx == 1) begin
              // Line is idle — ready to accept a new start bit
              rx_idle <= 1;
            end else if (rx == 0 && rx_idle) begin
              // Falling edge: start bit detected
              state    <= STATE_START;
              tick_cnt <= 0;
              rx_idle  <= 0;
            end
          end

          STATE_START: begin
            if (tick_cnt == 7) begin
              // We're at the middle of the start bit — verify it's still low
              if (rx == 0) begin
                state    <= STATE_DATA;
                tick_cnt <= 0;
                bit_idx  <= 0;
              end else begin
                // False start — go back to idle
                state <= STATE_IDLE;
              end
            end else begin
              tick_cnt <= tick_cnt + 1;
            end
          end

          STATE_DATA: begin
            if (tick_cnt == 15) begin
              // Sample at the middle-ish of each data bit
              rx_shift <= {rx, rx_shift[7:1]}; // LSB first: shift right
              tick_cnt <= 0;
              if (bit_idx == 7) begin
                state <= STATE_STOP;
              end else begin
                bit_idx <= bit_idx + 1;
              end
            end else begin
              tick_cnt <= tick_cnt + 1;
            end
          end

          STATE_STOP: begin
            if (tick_cnt == 15) begin
              if (rx == 1) begin
                // Valid stop bit — accept byte
                rx_done <= 1;
                rx_idle <= 1;
              end
              // Return to idle; rx_idle stays 0 on framing error,
              // so we won't mistake the lingering low for a start bit
              state <= STATE_IDLE;
            end else begin
              tick_cnt <= tick_cnt + 1;
            end
          end
        endcase
      end
    end
  end


  // ROT13
  wire [7:0] rx_byte = rx_shift;
  reg  [7:0] rot13_byte;

  always @(*) begin
    if ((rx_byte >= 8'd65 && rx_byte <= 8'd90)) begin
      // Uppercase A-Z
      if (rx_byte + 8'd13 > 8'd90)
        rot13_byte = rx_byte + 8'd13 - 8'd26;
      else
        rot13_byte = rx_byte + 8'd13;
    end else if ((rx_byte >= 8'd97 && rx_byte <= 8'd122)) begin
      // Lowercase a-z
      if (rx_byte + 8'd13 > 8'd122)
        rot13_byte = rx_byte + 8'd13 - 8'd26;
      else
        rot13_byte = rx_byte + 8'd13;
    end else begin
      // Unrecognized value, pass through
      rot13_byte = rx_byte;
    end
  end

  // Output register
  reg [7:0] out_reg;
  reg       data_valid;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      out_reg    <= 0;
      data_valid <= 0;
    end else begin
      data_valid <= 0; // default: clear strobe
      if (rx_done) begin
        out_reg    <= rot13_byte;
        data_valid <= 1;
      end
    end
  end

  assign uo_out  = out_reg;            // decoded byte on uo[0..7]
  assign uio_out = {7'b0, data_valid}; // data_valid on uio[0]
  assign uio_oe  = 8'b00000001;        // uio[0] is output, rest input

  // Unused inputs
  wire _unused = &{ena, ui_in[7:1], uio_in, 1'b0};

endmodule
